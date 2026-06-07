import os

from cs50 import SQL
from openai import OpenAI
import json
from flask import Flask, flash, redirect, render_template, request, session, abort, jsonify
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import login_required, logout_required, model_call
# Configure application
app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///Lumen.db")

# Initialize OpenAI client
client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1"
)

# List of all valid subjects for users to choose from when setting up their account
subjects = ["Math", "Philosophy", "Computer Science", "Biology", "Chemistry",
            "Physics", "History", "Literature", "Linguistics"]

# List of all valid difficulty levels
difficulty = ["Less comfortable", "More comfortable", "Very comfortable"]

# List of all valid Learning styles
Learning_styles = ["Strictly socratic, no hints allowed at all", "Socratic, but a few hints allowed",
                   "Socratic, but beginner level guidance"]

# List of all valid Goals
Goals = ["Exam preperation", "Understand a concept deeply", "Debug code (Experimental feature for computer science students)",
         "Learn from scratch", "Strengthen weak areas"]

# Ensure responses aren't cached


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
def index():
    """ Index/ homepage """

    if session.get("user_id") is None:
        # if user is not logged it
        return render_template("index.html")
    else:
        rows = db.execute("SELECT subject FROM subjects WHERE user_id = ?", session["user_id"])
        # if user already have subjects selected
        if rows:
            return redirect("/chat/history")
        # if user just logged in
        else:
            return redirect("/setup?mode=new_chat")


@app.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    """ Allow user to choose subjects """

    # User reached route via POST
    if request.method == "POST":
        # if user reached route via new_chat mode
        if request.args.get("mode") == "new_chat":

            # Get user's selected subject
            selected_subject = request.form.get("subject")
            app.logger.info(selected_subject)

            if not selected_subject:
                flash("Subject is required", "error")
                return redirect("/setup?mode=new_chat")

            # if the selected subject is in subjects table
            if db.execute("SELECT * FROM subjects WHERE user_id = ? AND subject = ?", session["user_id"], selected_subject):
                # Add NEW chat session to sessions table
                db.execute("INSERT INTO sessions (user_id, subject_id) VALUES(?, ?)", session["user_id"],
                        db.execute("SELECT id FROM subjects WHERE user_id = ? AND subject = ?", session["user_id"],
                        selected_subject)[0]["id"])

                flash("New chat session started", "success")

                # Get the ID of the row we JUST inserted
                session_id = db.execute("SELECT last_insert_rowid() AS id")[0]["id"]

                return redirect(f"/chat/{session_id}")

            # if the selected subject is not in subjects table with current user's id
            else:
                db.execute("INSERT INTO subjects (user_id, subject) VALUES(?, ?)",
                        session["user_id"], selected_subject)

                db.execute("INSERT INTO sessions (user_id, subject_id) VALUES(?, ?)", session["user_id"], db.execute(
                    "SELECT id FROM subjects WHERE user_id = ? AND subject = ?", session["user_id"], selected_subject)[0]["id"])

                flash("New chat session started!", "success")

                # Get the ID of the row we JUST inserted
                session_id = db.execute("SELECT last_insert_rowid() AS id")[0]["id"]

                return redirect(f"/chat/{session_id}")

        elif request.args.get("mode") == "getting_started":

            # Ensure User gave input
            if not request.form.get("difficulty"):
                flash("Difficulty is required", "error")
                return redirect("setup?mode=getting_started")

            elif not request.form.get("learning_style"):
                flash("Learning style is required", "error")
                return redirect("setup?mode=getting_started")

            elif not request.form.get("goal"):
                flash("Goal is required", "error")
                return redirect("setup?mode=getting_started")

            # Insert all user prefereces the user selected into the users table with the user's id
            db.execute("UPDATE users SET difficulty = ?, learning_style = ?, Goal = ? WHERE id = ?",
                    request.form.get("difficulty"), request.form.get("learning_style"), request.form.get("goal"), session["user_id"])

            flash("Account setup successful! You can now start chatting with Lumen.", "success")

            return redirect("/setup?mode=new_chat")

    # User reached the route via GET
    else:

        if request.args.get("mode") == "new_chat":
            return render_template("setup.html", subjects=subjects, mode=request.args.get("mode"))

        elif request.args.get("mode") == "getting_started":

            # Make sure this is the user's first time logging in
            rows = db.execute("SELECT difficulty, learning_style, Goal FROM Users WHERE id = ?", session["user_id"])

            # if rows have data associated with the user's account
            if rows == None:
                return redirect("/setup?mode=new_chat")
            # if the query result is empty
            else:
                return render_template("setup.html", difficulty=difficulty, Learning_styles=Learning_styles, Goals=Goals, mode=request.args.get("mode"))


@app.route("/chat/history", methods=["GET", "POST"])
@login_required
def chat_history():
    """ Display chat history """

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # if user clicked start new chat button
        if "new_chat" in request.form:
            #redirect the user to setup route
            return redirect("/setup?mode=new_chat")

    # if the user reached route via GET (as by clicking a link or via redirect)
    else:
        # query for all sessions to display
        chat_sessions = db.execute("SELECT * FROM sessions WHERE user_id = ?", session["user_id"])

        # get the subject for each chat session from subjects table and add it to the chat_sessions list
        for chat_session in chat_sessions:
            chat_session["subject"] = db.execute(
                "SELECT subject FROM subjects WHERE id = ?", chat_session["subject_id"])[0]["subject"]

        return render_template("chat_history.html", subjects=subjects, chat_sessions=chat_sessions)


@app.route("/chat/<session_id>", methods=["GET", "POST"])
@login_required
def chat_session(session_id):
    """ View a specific chat session """

    # check if the session_id is valid and belongs to the current user
    if not db.execute("SELECT * FROM sessions WHERE id = ? AND user_id = ?", session_id, session["user_id"]):
        abort(404)

    # Fetch the selected subject for the current chat session from sessions table with the session_id
    selected_subject = db.execute("SELECT subject FROM subjects WHERE id = ?",
                                  db.execute("SELECT subject_id FROM sessions WHERE id = ?", session_id)[0]["subject_id"])[0]["subject"]

    user_difficulty = db.execute("SELECT difficulty FROM users WHERE id = ?", session["user_id"])[0]["difficulty"]
    Learning_style = db.execute("SELECT learning_style FROM users WHERE id = ?", session["user_id"])[0]["learning_style"]
    Goal = db.execute("SELECT Goal FROM users WHERE id = ?", session["user_id"])[0]["Goal"]

    # Create a system prompt for the AI agent to follow based on the selected subject for the current chat session
    system_prompt = (f"You are Lumen, a socratic AI assistant designed to help students learn by asking thought-provoking questions. You have access to the user's selected subject for this session, which is {selected_subject}. "
                     f"You must never answer user's question directly. make sure to ask questions that guide the user to think critically and arrive at the answer on their own. "
                     f"Make sure you respond to the user's input based on these user preferences: user is {user_difficulty} learning with socratic method,"
                     f"user's prefered learning style: {Learning_style} and User's Main Goal for using Lumen (avoid if not applicable to {selected_subject}): {Goal} "
                     f"Engage warmly with the user's response before asking your next question. Acknowledge what they said, build on it, then guide them further with one focused question. "
                     f"Always be respectful and encouraging in your responses yet display a socratic personality in your responses. Your goal is to foster a deep understanding of the subject matter and promote independent thinking. "
                     f"The user is a student seeking help with their studies, and you are here to assist them in their learning journey. if the user asks you a question urelated to the current subjects they are studying, "
                     f"respond with a gentle reminder to stay focused on their studies and ask if they have any questions related to the subjects they are studying, however, if a topic, person, or work has any connection with the subject, "
                     f"then that topic is relevant to the discussion. also if the user asks you to directly answer their question, respond with a gentle reminder that you are designed to facilitate learning through questioning, not direct answering. "
                     f"even if the user's response is vague , if it is in any way related to the {selected_subject}, you should guide him by asking possible questions about {selected_subject}."
                     f"Act like socrates in all your responses regardless of the user's tone or behavior, and always ask questions that forces the user to think crtically about the topic at hand. never break character. "
                     f"Adjust your personality according to the user's tone, and the subject they are studying.")

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # check if user input is in the request form
        if not request.json.get("user_input"):
            return jsonify({"ai_response": "User input is required"}), 400

        user_input = request.json.get("user_input")
        summary_status = db.execute("SELECT session_summary FROM sessions WHERE id = ?", session_id)

        # if the summary is NULL then generate summary
        if summary_status[0]["session_summary"] == None:

            model = "llama-3.3-70b-versatile"

            user_prompt = (
                f"Summarize the following conversation in about 10 words based on {user_input}"
                        f"You won't be given entire conversation, you must summarize based on {user_input} only. "
                        f"if the input is irrelevant to {selected_subject}, return exactly: 'irrelevant input'"
                        f"summarize the conversation don't answer to: {user_input}"
                        f"If the topic in user input is such that crosses the lines of two subjects don't return irrelevant"
                        f"even if the user input: {user_input} is vague, you should only respond exactly with the words:'irrelevant input', "
                        f"when the user input is not in the scope of the subject, you must not return anything else in this case,"
                        f"not when the user's answer is wrong : {user_input}"
            )

            summary = model_call(system_prompt, user_prompt, model)

            db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)",
                       session_id, "user", user_input)

            summary_result = summary.choices[0].message.content.lower().strip(".")

            # if the summary response is "irrelevant input"
            if summary_result == "irrelevant input":
                # Generate a reminder for the user to stay focused on the subject matter

                user_prompt = (
                     f"Respond with a gentle reminder to stay focused on their studies"
                         f"and ask if they have any questions related to the {selected_subject}"
                         f"since the user input is irrelevant to their studies: {user_input}"
                )

                response = model_call(system_prompt, user_prompt)

                db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)",
                           session_id, "assistant", response.choices[0].message.content)

                return jsonify({"ai_response": response.choices[0].message.content}), 200

            # otherwise, insert the summary into the sessions table and continue with the conversation as normal
            else:
                db.execute("UPDATE sessions SET session_summary = ? WHERE id = ?",
                           summary.choices[0].message.content, session_id)

                # continue with the conversation as normal and get the AI response based on the user input and system prompt
                user_prompt = user_input
                response = model_call(system_prompt, user_prompt)

                db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)",
                           session_id, "assistant", response.choices[0].message.content)
                return jsonify({"ai_response": response.choices[0].message.content}), 200

        # otherwise, when session_summary != NULL, insert the user input and AI response into messages and continue with the conversation as normal
        else:
            # fetch chat history from messages table
            chat_history = db.execute("SELECT * FROM messages WHERE session_id = ?", session_id)

            # Build messages list for API
            messages = [{"role": "system", "content": system_prompt}]

            # Add chat history to messages list
            for message in chat_history:
                messages.append({"role": message["role"], "content": message["content"]})

            # Append current user message to messages list
            messages.append({"role": "user", "content": user_input})

            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages
            )

            db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)",
                       session_id, "user", user_input)
            db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)",
                       session_id, "assistant", response.choices[0].message.content)

            # to get the current count of messages for current session
            message_count = db.execute(
                "SELECT COUNT(*) as count FROM messages WHERE session_id = ?", session_id)[0]["count"]

            if message_count % 5 == 0:
                # Get last 10 messages from history
                recent_messages = db.execute(
                    "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT 10", session_id)

                # Reverse so chronological order
                recent_messages = recent_messages[::-1]

                clean_history = [{"role": msg["role"], "content": msg["content"]}
                                 for msg in recent_messages]

                existing_topics = db.execute("SELECT topic, depth FROM topics WHERE user_id = ? AND session_id = ?", session["user_id"], session_id)

                app.logger.info(f"Topics: {existing_topics}")

                # Feed all messages into the API call and ask for returning all unique topic discussed across all sessions by subject

                system_prompt = (f"You need to return all unique topics discussed in the message exchanges."
                                 f"you are required to return a JSON file as your response. No preamble, no markdown backticks, just raw JSON."
                                 f"Already covered topics: {existing_topics}. Only return NEW topics not already in this list."
                                 f"Topics must be explained relative to the depth they were discussed in the conversation."
                                 f"the Topics you return must be widely recognizable by name, such as 'thermodynamics' in science,"
                                 f"Only generate a topic if it is genuinely distinct from all topics in the existing topics list. Subtopics and variations do not qualify."
                                 f"Just return the topic that can encapsulate the entirety of that conversational exchange in it, without losing any relevant change."
                                 f"Each topic must include a brief 1-2 sentence explanation of the depth and context in which it was discussed."
                                 f"your response must be acurrate and not mix topics from one subject to another, or overestimate the depth of the discussion"
                                 f"If multiple topics are clearly part of the same broader concept, merge them into one. For example, backend and frontend development are both Software Development."
                                 f"You'll be given message history of all chat sessions they user ever had in the user prompt.")

                user_prompt = (
                    f"Now return a JSON array of objects, each with a 'topic' and 'explanation' key. No subject keys."
                              f"Always return a JSON array, even if there is only one topic. Never return a single object."
                              f"with breif explanation of the depth covered."
                )

                return_type = "JSON"

                Topics = model_call(system_prompt, user_prompt, return_type, clean_history)

                # Returns a JSON which is a dict where each key stores a list that stores a dict with keys topic and depth
                topics = json.loads(Topics.choices[0].message.content)
                app.logger.info(f"Topics structure: {topics}")

                # Check if the Model returned a list or a single dict object
                if isinstance(topics, list):
                    topics_list = topics
                elif "topic" in topics:
                    topics_list = [topics]  # single dict, wrap it
                else:
                    topics_list = list(topics.values())

                for topic in topics_list:
                    db.execute("INSERT INTO topics (topic, depth, user_id, session_id) VALUES(?, ?, ?, ?)",
                            topic["topic"], topic["explanation"], session["user_id"], session_id)

            return jsonify({"ai_response": response.choices[0].message.content}), 200

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Only greet the user if there is no field in messages table for current session_id
        if not db.execute("SELECT * FROM messages WHERE session_id = ?", session_id):
            username = db.execute("SELECT username FROM users WHERE id = ?",
                                  session["user_id"])[0]["username"]

            user_prompt = f"Greet {username} and ask how you can assist them with their studies today."
            response = model_call(system_prompt, user_prompt)

            db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)",
                       session_id, "assistant", response.choices[0].message.content)
            chat_history = db.execute("SELECT * FROM messages WHERE session_id = ?", session_id)
            return render_template("chat_interface.html", session_id=session_id, chat_history=chat_history)

        # get chat history from messages table with the session_id and render the chat interface
        else:
            chat_history = db.execute("SELECT * FROM messages WHERE session_id = ?", session_id)
            return render_template("chat_interface.html", session_id=session_id, chat_history=chat_history)


@app.route("/login", methods=["GET", "POST"])
@logout_required
def login():
    """ Log user in """

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            flash("Username is required", "error")
            return render_template("login.html")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("Password is required", "error")
            return render_template("login.html")

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["password_hash"], request.form.get("password")
        ):
            flash("Invalid username or password", "error")
            return render_template("login.html")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
@logout_required
def register():
    """ Register new users """

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            flash("Username is required", "error")
            return render_template("register.html")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("Password is required", "error")
            return render_template("register.html")

        # Ensure conformation match with password
        elif request.form.get("password") != request.form.get("confirmation"):
            flash("Passwords do not match", "error")
            return render_template("register.html")

        # Generate hash for the password
        hash_pass = generate_password_hash(request.form.get("password"))

        # Check if username already taken
        try:

            db.execute("INSERT INTO users (username, password_hash) VALUES(?, ?)",
                       request.form.get("username"), hash_pass)

            # Log the user in by remembering their user_id in session
            session["user_id"] = db.execute(
                "SELECT id FROM users WHERE username = ?", request.form.get("username"))[0]["id"]

            flash("Registration successful! Please setup your account.", "success")
            return redirect("/setup?mode=getting_started")

        except ValueError:

            flash("Username already taken", "error")
            return render_template("register.html")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    """ Log user out """

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/dashboard")
@login_required
def dashboard():
    """ Display user stats """

    subjects_enrolled = db.execute(
        "SELECT DISTINCT subject FROM subjects WHERE user_id = ?", session["user_id"])

    # Get all active sessions per subject the user currently have
    sessions_bysubjects = (db.execute(
        "SELECT subjects.subject, COUNT(sessions.id) as session_count FROM sessions JOIN subjects ON sessions.subject_id = subjects.id WHERE sessions.user_id = ? GROUP BY subjects.subject", session["user_id"]))

    # Connection between topics across different subjects
    # Get all topics by subject for current user
    All_topics = db.execute(
        "SELECT topics.topic , subjects.subject FROM topics INNER JOIN sessions ON topics.session_id = sessions.id INNER JOIN subjects ON sessions.subject_id = subjects.id WHERE topics.user_id = ?", session["user_id"])

    app.logger.info(All_topics)

    system_prompt = (
        f"You will be given a list of topics, and the subject they were discussed in, Your task is to return connecting topics across subjects in a JSON file, "
        f"with subjects and connection as keys and the name of subjects that are connected and a quick 1-2 paragraph summary of how the topics connect as their values."
    )

    topic = []
    for index in range(len(All_topics)):
        topic.append("topic: "All_topics[index]["topic"], "subject: "All_topics[index]["subject"])

    user_prompt =

    # Give all topics to the Model and ask it to return connected topics across subjects and a summary response on how they are related
    Connection = model_call(system_prompt, user_prompt)

    return render_template("dashboard.html", subjects=subjects_enrolled, sessions=sessions_bysubjects)
