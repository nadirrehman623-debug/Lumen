import os

from cs50 import SQL
from flask import redirect, session
from openai import OpenAI
from datetime import datetime
import json
from functools import wraps

# Initialize OpenAI client
client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1"
)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///Lumen.db")


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


def logout_required(f):
    """
    Decorate routes to require logout.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is not None:
            return redirect("chat/history")
        return f(*args, **kwargs)

    return decorated_function


def model_call(system_prompt,  user_prompt, return_type="string", history = None, api_model="openai/gpt-oss-120b"):
    """
    Make the call to the LLM.
    default model = openai/gpt-oss-120b
    default return_type = strings
    """

    if return_type == "string":
         response = client.chat.completions.create(
                    model= api_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )

         return response # for return type 'str'

    else:
         if history:
            response = client.chat.completions.create(
                        model= api_model,
                        response_format={"type": "json_object"}, # Returns a JSON
                        messages=[{"role": "system", "content": system_prompt}]
                                + history +
                                [{"role": "user", "content": user_prompt}]
                    )

            return response

         else:
            response = client.chat.completions.create(
                    model= api_model,
                    response_format={"type": "json_object"}, # Returns a JSON
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )

         return response

def summary_generator(user_input, selected_subject, system_prompt, session_id):
    """ Generate summary for sessions """

    summary_prompt = system_prompt + (
        f"Summarize the potential scope of a conversation in about 10 words based on {user_input} "
        f"you must not mention anything like 'user asked to generate summary' or 'summarise in 10 words'. "
        f"You won't be given entire conversation, you must summarize based on user's first response:{user_input} only. "
        f"if user's response is irrelevant to {selected_subject}, return exactly: 'irrelevant input', "
        f"the summary should not be a generic 'discussing {selected_subject} deeply', if there's nothing to summarize yet, just return 'irrelevant input' "
        f"when the user input is not in the scope of {selected_subject}, you must not return anything else, just:'irrelevant input' "
        f"If the user's response: {user_input} is vague, you should only respond exactly with the words:'irrelevant input', "
        f"your only task is to summarize the conversation's scope based on what the user's response: {user_input} is, "
        f"and what's being asked, you should not answer to the user's response:{user_input}, only summarize the possible conversation. "
        f"If the topic in user's response is such that crosses the lines between two subjects don't return irrelevant, "
        f"if the user's response:{user_input} is wrong but within the scope of {selected_subject}, "
        f"don't use subject name like 'mathematically', 'biologically', 'philosophically' unless the user's response demands that word expicitly,"
        f"or add 'deeply' to the summary. you must still return just:'irrelevant input'."
    )

    user_prompt = f"user's response: {user_input} to summarize."

    model = "llama-3.3-70b-versatile"

    summary = model_call(summary_prompt, user_prompt, api_model=model)

    db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)",
                session_id, "user", user_input)

    summary_result = summary.choices[0].message.content

    return summary_result


def sessions_history():
    """ Return all user sessions """

    chat_sessions = db.execute("SELECT * FROM sessions WHERE user_id = ?", session["user_id"])

    # get the subject for each chat session from subjects table and add it to the chat_sessions list
    for chat_session in chat_sessions:
        chat_session["subject"] = db.execute(
            "SELECT subject FROM subjects WHERE id = ?", chat_session["subject_id"])[0]["subject"]
        created = datetime.strptime(chat_session["created_at"], "%Y-%m-%d %H:%M:%S")
        diff = datetime.now() - created

        if diff.days > 0:
            chat_session["time_ago"] = f"{diff.days} days ago"
        elif diff.seconds // 3600 > 0:
            chat_session["time_ago"] = f"{diff.seconds // 3600} hours ago"
        else:
            chat_session["time_ago"] = f"{diff.seconds // 60} minutes ago"

    return chat_sessions


def topics_generator(session_id):
    """ generate topics from messages """

    message_count = db.execute(
                "SELECT COUNT(*) as count FROM messages WHERE session_id = ?", session_id)[0]["count"]

    # To delay model call for topic generation
    if message_count % 5 == 0:
        # Get last 10 messages from history
        recent_messages = db.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT 10", session_id)

        # Reverse so chronological order
        recent_messages = recent_messages[::-1]

        clean_history = [{"role": msg["role"], "content": msg["content"]}
                            for msg in recent_messages]

        All_topics = db.execute("SELECT topic FROM topics WHERE user_id = ? AND session_id = ?", session["user_id"], session_id)

        existing_topics = clean_list(All_topics)

        # Feed all messages into the API call and ask for returning all unique topic discussed across all sessions by subject
        system_prompt = (
            f"You need to return all unique topics discussed in the message exchanges."
                            f"you are required to return a JSON file as your response. No preamble, no markdown backticks, just raw JSON. "
                            f"Already covered topics list: {existing_topics}. Only return NEW topics not already in this list. "
                            f"the Topics you return must be widely recognizable by name, such as 'thermodynamics' in science, "
                            f"Only generate a topic if it is genuinely distinct from all topics in the existing topics list. Subtopics and variations do not qualify. "
                            f"Just return the topic that can encapsulate the entirety of that conversational exchange in it, without losing any relevant change. "
                            f"your response must be acurrate and not mix topics from one subject to another, "
                            f"If multiple topics are clearly part of the same broader concept, merge them into one. "
                            f"For example, backend and frontend development are both Software Development. "
                            f"You'll be given message history of all chat sessions they user ever had in the user prompt. "
        )

        user_prompt = (
            f"Now return a JSON array of objects, each with a 'topic' key. No subject keys."
                        f"Always return a JSON array, even if there is only one topic. Never return a single object."
        )

        Topics = model_call(system_prompt, user_prompt, return_type="JSON", history=clean_history)

        # Returns a JSON which is a dict where each key stores a list that stores a dict with keys topic and depth
        topics = json.loads(Topics.choices[0].message.content)

        # Check if the Model returned a list or a single dict object
        if isinstance(topics, list):
            topics_list = topics
        elif "topic" in topics:
            topics_list = [topics]  # single dict, wrap it
        else:
            topics_list = list(topics.values())

        for topic in topics_list:
            db.execute("INSERT INTO topics (topic, user_id, session_id) VALUES(?, ?, ?)",
                    topic["topic"], session["user_id"], session_id)



def clean_list(list):
    """
    Takes a list of dicts and
    returns a list of values
    """

    cleanlist = []

    if list:
        for index in list:
             for key in index:
                cleanlist.append(index[key])

    return cleanlist
