import os

from cs50 import SQL
from openai import OpenAI
import json
from flask import Flask, flash, redirect, render_template, request, session, abort, jsonify
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import login_required, logout_required, model_call, summary_generator, topics_generator, sessions_history, clean_list
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

# List of all valid subjects for users to choose from
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
        return render_template("index.html")
    else:
        rows = db.execute("SELECT subject FROM subjects WHERE user_id = ?", session["user_id"])
        if rows:
            return redirect("/chat/history")
        else:
            return redirect("/setup?mode=new_chat")


@app.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    """ Allow user to choose subjects & setup user_preferences """

    # User reached route via POST
    if request.method == "POST":
        # if user reached route via new_chat mode
        if request.args.get("mode") == "new_chat":

            selected_subject = request.form.get("subject")

            if not selected_subject:
                flash("Subject is required", "danger")
                return redirect("/setup?mode=new_chat")

            # if the selected subject is in subjects table
            if db.execute("SELECT * FROM subjects WHERE user_id = ? AND subject = ?", session["user_id"], selected_subject):
                # Add NEW chat session to sessions table
                db.execute("INSERT INTO sessions (user_id, subject_id) VALUES(?, ?)", session["user_id"],
                        db.execute("SELECT id FROM subjects WHERE user_id = ? AND subject = ?", session["user_id"],
                        selected_subject)[0]["id"])

                # Get the ID of the row we JUST inserted
                session_id = db.execute("SELECT last_insert_rowid() AS id")[0]["id"]

                if selected_subject:
                    flash("New chat session started", "success")

                return redirect(f"/chat?mode=session_{session_id}")

            # if the selected subject is not in subjects table with current user's id
            else:
                db.execute("INSERT INTO subjects (user_id, subject) VALUES(?, ?)",
                        session["user_id"], selected_subject)

                db.execute("INSERT INTO sessions (user_id, subject_id) VALUES(?, ?)", session["user_id"], db.execute(
                    "SELECT id FROM subjects WHERE user_id = ? AND subject = ?", session["user_id"], selected_subject)[0]["id"])

                session_id = db.execute("SELECT last_insert_rowid() AS id")[0]["id"]

                if selected_subject:
                    flash("New chat session started", "success")

                return redirect(f"/chat?mode=session_{session_id}")

        elif request.args.get("mode") == "getting_started":

            # Ensure User gave input
            if not request.form.get("difficulty"):
                flash("Difficulty is required", "danger")
                return redirect("setup?mode=getting_started")

            elif not request.form.get("learning_style"):
                flash("Learning style is required", "danger")
                return redirect("setup?mode=getting_started")

            elif not request.form.get("goal"):
                flash("Goal is required", "danger")
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


@app.route("/chat", methods=["GET", "POST"])
@login_required
def chat():
    """ Chat interface """

    mode = request.args.get("mode")

    if mode and mode.startswith("session_"):

        session_id = int(mode.split("_")[1])

        # Fetch the selected subject for the current chat session from sessions table with the session_id
        selected_subject = db.execute("SELECT subject FROM subjects WHERE id = ?",
                                    db.execute("SELECT subject_id FROM sessions WHERE id = ?", session_id)[0]["subject_id"])[0]["subject"]
    else:
        selected_subject = "None"

    user_difficulty = db.execute("SELECT difficulty FROM users WHERE id = ?", session["user_id"])[0]["difficulty"]
    Learning_style = db.execute("SELECT learning_style FROM users WHERE id = ?", session["user_id"])[0]["learning_style"]
    Goal = db.execute("SELECT Goal FROM users WHERE id = ?", session["user_id"])[0]["Goal"]

    # Create a system prompt for the AI agent to follow based on the selected subject for the current chat session
    system_prompt = (
        f"You are Lumen, a socratic AI assistant designed to help students learn by asking thought-provoking questions."
                     f"The user is a student seeking help with their studies, and you are here to assist them in their learning journey."
                     f"You have access to the user's selected subject for this session, which is {selected_subject}. You must never answer user's question directly. "
                     f"Make sure to ask questions that guide the user to think critically and arrive at the answer on their own. "
                     f"Make sure you respond to the user's input based on these user preferences: user is {user_difficulty} learning with socratic method,"
                     f"user's prefered learning style: {Learning_style} and User's Main Goal for using Lumen (avoid if not practically applicable to {selected_subject}): {Goal} "
                     f"Engage warmly with the user's response before asking your next question. Acknowledge what they said, build on it, then guide them further with one focused question. "
                     f"Always be respectful and encouraging in your responses yet display a socratic personality in your responses. "
                     f"Your goal is to foster a deep understanding of the subject matter and promote independent thinking. "
                     f"If the user asks you a question urelated to the current subjects they are studying, respond with a gentle reminder to stay focused on their studies, "
                     f"and ask if they have any questions related to the subjects they are studying, however, if a topic, person, or work has any connection with the subject, "
                     f"then that topic is relevant to the discussion. also if the user asks you to directly answer their question, "
                     f"respond with a gentle reminder that you are designed to facilitate learning through questioning, not direct answering."
                     f"even if the user's response is vague and confusing , if it is in any way related to the {selected_subject}, you should guide him by asking possible questions about {selected_subject}."
                     f"Act like socrates in all your responses regardless of the user's tone or behavior, "
                     f"respond with a gentle reminder that you are designed to facilitate learning through questioning, not direct answering. "
                     f"Adjust your personality according to the user's tone, and the subject they are studying."
    )

    # User reached route via POST
    if request.method == "POST":

        if mode == "sessions":
            # if user clicked start new chat button
            if "new_chat" in request.form:
                return redirect("/setup?mode=new_chat")

            else:
                sessions_ids = db.execute("SELECT id FROM sessions WHERE user_id = ?", session["user_id"])

                session_ids = clean_list(sessions_ids) # get the values only!

                for id in session_ids:
                    if id in request.form:
                        db.execute("DELETE FROM sessions WHERE id = ?", id)
                        return redirect("/chat?mode=sessions")

        elif mode and mode.startswith("session_"):

            # check if the session_id is valid and belongs to the current user
            if not db.execute("SELECT * FROM sessions WHERE id = ? AND user_id = ?", session_id, session["user_id"]):
                abort(404)

            if not request.json.get("user_input"):
                return jsonify({"ai_response": "User input is required"}), 400

            user_input = request.json.get("user_input")

            summary_status = db.execute("SELECT session_summary FROM sessions WHERE id = ?", session_id)

            if summary_status[0]["session_summary"] == None:

                summary_result = summary_generator(user_input, selected_subject, system_prompt, session_id)

                summary_check = summary_result.lower().strip(".")

                # if the summary response is "irrelevant input"
                if summary_check == "irrelevant input":

                    user_prompt = (
                            f"Respond with a gentle reminder to stay focused on their studies"
                                f"and ask if they have any questions related to the {selected_subject}"
                                f"since their response is irrelevant to their studies: {user_input}"
                    )

                    response = model_call(system_prompt, user_prompt)

                    db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)",
                                session_id, "assistant", response.choices[0].message.content)

                    return jsonify({"ai_response": response.choices[0].message.content}), 200

                # Otherwise, insert the summary into the sessions table and continue with the conversation as normal
                else:
                    db.execute("UPDATE sessions SET session_summary = ? WHERE id = ?",
                                summary_result, session_id)

                    # Continue with the conversation as normal and get the AI response based on the user input and system prompt
                    user_prompt = user_input
                    response = model_call(system_prompt, user_prompt)

                    db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)",
                                session_id, "assistant", response.choices[0].message.content)
                    return jsonify({"ai_response": response.choices[0].message.content}), 200

            # otherwise, when session_summary != None, insert the user input and AI response into messages
            else:
                chat_history = db.execute("SELECT * FROM messages WHERE session_id = ?", session_id)

                # Build messages list for contextualizing the conversation for the API
                messages = [{"role": "system", "content": system_prompt}]

                # Add chat history to messages list
                for message in chat_history:
                    messages.append({"role": message["role"], "content": message["content"]})

                messages.append({"role": "user", "content": user_input})

                response = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=messages
                )

                db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)",
                        session_id, "user", user_input)
                db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)",
                        session_id, "assistant", response.choices[0].message.content)

                topics_generator(session_id)

                return jsonify({"ai_response": response.choices[0].message.content}), 200

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        if mode and mode.startswith("session_"):

            chat_sessions = sessions_history()

            # Only greet the user if there is no field in messages table for current session_id
            if not db.execute("SELECT * FROM messages WHERE session_id = ?", session_id):
                username = db.execute("SELECT username FROM users WHERE id = ?",
                                    session["user_id"])[0]["username"]

                user_prompt = f"Greet {username} and ask how you can assist them with their studies today."
                response = model_call(system_prompt, user_prompt)

                db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)",
                        session_id, "assistant", response.choices[0].message.content)

                chat_history = db.execute("SELECT * FROM messages WHERE session_id = ?", session_id)

                return render_template("chat_interface.html", session_id=session_id, chat_history=chat_history, chat_sessions=chat_sessions)

            # Get chat history from messages table with the session_id and render the chat interface
            else:
                chat_history = db.execute("SELECT * FROM messages WHERE session_id = ?", session_id)
                return render_template("chat_interface.html", session_id=session_id, chat_history=chat_history, chat_sessions=chat_sessions)

        elif mode == "sessions":
            chat_sessions = sessions_history()
            return render_template("chat_interface.html", chat_sessions=chat_sessions)

        else:
            rows = db.execute("SELECT * FROM sessions WHERE user_id = ?", session["user_id"])
            if not rows:
                return render_template("chat_interface.html")
            else:
                return redirect("/chat?mode=sessions")


@app.route("/chat/history")
@login_required
def chat_history():
    """ Display All sessions alognside the subjects and the time """
    chat_sessions = sessions_history()
    return render_template("chat_history.html", chat_sessions=chat_sessions)


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
            flash("Username is required", "danger")
            return render_template("login.html")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("Password is required", "danger")
            return render_template("login.html")

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["password_hash"], request.form.get("password")
        ):
            flash("Invalid username or password", "danger")
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

        if not request.form.get("username"):
            flash("Username is required", "danger")
            return render_template("register.html")

        elif not request.form.get("password"):
            flash("Password is required", "danger")
            return render_template("register.html")

        elif request.form.get("password") != request.form.get("confirmation"):
            flash("Passwords do not match", "danger")
            return render_template("register.html")

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

            flash("Username already taken", "danger")
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


@app.route("/Correlations", methods=["GET", "POST"])
@login_required
def Correlations():
    """ Display Correlation between Topics """

    # if User reached the route via POST
    if request.method == "POST":


        All_topics = db.execute(
            "SELECT topics.topic , subjects.subject FROM topics INNER JOIN sessions ON topics.session_id = sessions.id INNER JOIN subjects ON sessions.subject_id = subjects.id WHERE topics.user_id = ?", session["user_id"])

        if All_topics:

            # Constructing user prompt from all topics
            topics = []
            for index in range(len(All_topics)):
                topics.append("topic: " + All_topics[index]["topic"])
                topics.append("subject: " + All_topics[index]["subject"])
                if index > 0 and index < len(All_topics) - 1:
                    topics.append(",")

            user_prompt = " ".join(topics)

            # Get connected topics from connections table
            connected_topics = db.execute("SELECT connection FROM connections WHERE user_id = ?", session["user_id"])

            # Clean list of connected topics
            existing_correlations = clean_list(connected_topics)

            system_prompt = (
                f"You will be given a list of topics, and the subject they were discussed in, Your task is to return connecting topics across subjects in a JSON file, "
                f"Always return a JSON array, and within that file, subjects, connection and summary as keys to the name of subjects that are connected, "
                f"the topics that are connected and a concise 1-2 paragraph summary of how the topics connect as their values. and the values must be strings, not lists. "
                f"Already connected topic pairs: {existing_correlations}. Only return NEW connections not already in this list. "
                f"Each pair of connected subjects must be seperated by 'and' not '-' or ',' or any other punctuations, "
                f"if no topics are connected, return an empty JSON object not an empty list, the connected topics must have different subjects. "
                f"Only generate a connection if the two topics share a direct and non-trivial conceptual overlap. Avoid forcing connections, "
                f"Return connections that has meaningful overlap and is genuinely study-able on it's own, not connections that just have some similar aspects but are largly unrelated. "
                f"Do not generate connections based on loose thematic similarity or forced analogies. If you have to stretch to make the connection, do not include it. "
                f"A valid connection is one that a professor teaching both subjects would assign as a cross-disciplinary reading."
            )

            Correlation = model_call(system_prompt, user_prompt, return_type="JSON")

            Correlations = json.loads(Correlation.choices[0].message.content)

            # Check if the Model returned a list or a dict object
            if isinstance(Correlations, list):
                db.execute("INSERT INTO connections (user_id, subjects, connection, summary) VALUES(?, ?, ?, ?)",
                        session["user_id"], Correlations[0]["subjects"], Correlations[0]["connection"], Correlations[0]["summary"])
            else:
                if Correlations:
                    db.execute("INSERT INTO connections (user_id, subjects, connection, summary) VALUES(?, ?, ?, ?)",
                            session["user_id"], Correlations["subjects"], Correlations["connection"], Correlations["summary"])

            return redirect("/Correlations")

        else:
            flash("No topics to generate Correlations yet!", "danger")
            return redirect("/Correlations")

    # User reached the route via GET
    else:

        Correlations = db.execute("SELECT * FROM connections WHERE user_id = ?", session["user_id"])

        # Storing all Correlations that share same pair of subjects together
        grouped = {}
        for corr in Correlations:
            key = corr["subjects"]
            grouped.setdefault(key, []).append(corr)


        return render_template("Correlations.html", Correlations=grouped)


@app.route("/dashboard")
@login_required
def dashboard():
    """ Display user info """

    subjects_enrolled = db.execute(
            "SELECT DISTINCT subject FROM subjects WHERE user_id = ?", session["user_id"])

    # Get all active sessions per subject the user currently have
    sessions_bysubjects = (db.execute(
        "SELECT subjects.subject, COUNT(sessions.id) as session_count FROM sessions JOIN subjects ON sessions.subject_id = subjects.id WHERE sessions.user_id = ? GROUP BY subjects.subject", session["user_id"]))

    user_info = db.execute("SELECT username, difficulty, learning_style, Goal FROM users WHERE id = ?", session["user_id"])

    return render_template("dashboard.html",  subjects=subjects_enrolled, sessions=sessions_bysubjects, user_info=user_info, difficulty=difficulty, Learning_styles=Learning_styles, Goals=Goals)
