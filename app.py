import os

from cs50 import SQL
from openai import OpenAI
from flask import Flask, flash, redirect, render_template, request, session, abort
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import login_required
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
        # User reached route via GET (as by clicking a link or via redirect)
        return render_template("index.html")
    else:
        rows = db.execute("SELECT subject FROM subjects WHERE user_id = ?", session["user_id"])
        if rows:
            return redirect("/chat/history")
        else:
            return redirect("/setup")


@app.route("/chat/history", methods=["GET", "POST"])
@login_required
def chat_history():
    """ Display chat history """

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        selected_subject = request.form.get("subject")
        if not selected_subject:
            flash("Subject is required", "error")
            chat_sessions = db.execute(
                "SELECT * FROM sessions WHERE user_id = ?", session["user_id"])
            return render_template("chat_history.html", subjects=subjects, chat_sessions=chat_sessions)

        # if the selected subject is in subjects table with current user's id, then add new chat session to sessions table
        if db.execute("SELECT * FROM subjects WHERE user_id = ? AND subject = ?", session["user_id"], selected_subject):
            db.execute("INSERT INTO sessions (user_id, subject_id, subject) VALUES(?, ?, ?)", session["user_id"], db.execute(
                "SELECT id FROM subjects WHERE user_id = ? AND subject = ?", session["user_id"], selected_subject)[0]["id"], selected_subject)

        # if the selected subject is not in subjects table with current user's id
        else:
            db.execute("INSERT INTO subjects (user_id, subject) VALUES(?, ?)",
                       session["user_id"], selected_subject)
            db.execute("INSERT INTO sessions (user_id, subject_id, subject) VALUES(?, ?, ?)", session["user_id"], db.execute(
                "SELECT id FROM subjects WHERE user_id = ? AND subject = ?", session["user_id"], selected_subject)[0]["id"], selected_subject)

        flash("New chat session started!", "success")
        session_id = db.execute("SELECT id FROM sessions WHERE user_id = ? AND subject = ?", session["user_id"], selected_subject)
        return redirect(f"/chat/{session_id[0]['id']}")

    # if the user reached route via GET (as by clicking a link or via redirect)
    else:
        chat_sessions = db.execute("SELECT * FROM sessions WHERE user_id = ?", session["user_id"])
        return render_template("chat_history.html", subjects=subjects, chat_sessions=chat_sessions)



@app.route("/chat/<session_id>", methods=["GET", "POST"])
@login_required
def chat_session(session_id):
    """ View a specific chat session """

    # check if the session_id is valid and belongs to the current user
    if not db.execute("SELECT * FROM sessions WHERE id = ? AND user_id = ?", session_id, session["user_id"]):
        abort(404)

    # get the selected subject for the current chat session from sessions table with the session_id
    selected_subject = db.execute(
        "SELECT subject FROM sessions WHERE id = ?", session_id)

    # create a system prompt for the AI agent to follow based on the selected subject for the current chat session
    system_prompt = (f"You are Lumen, a socratic AI assistant designed to help students learn by asking thought-provoking questions. You have access to the user's selected subject for this session, which is {selected_subject}. "
                     f"You must never answer user's question directly. make sure to ask questions that guide the user to think critically and arrive at the answer on their own. "
                     f"Always be respectful and encouraging in your responses yet display a socratic personality in your responses. Your goal is to foster a deep understanding of the subject matter and promote independent thinking. "
                     f"The user is a student seeking help with their studies, and you are here to assist them in their learning journey. if the user asks you a question urelated to the current subjects they are studying, "
                     f"respond with a gentle reminder to stay focused on their studies and ask if they have any questions related to the subjects they are studying. also if the user asks you to directly answer their question, "
                     f"respond with a gentle reminder that you are designed to facilitate learning through questioning, not direct answering. Act like socrates in all your responses regardless of the user's tone or behavior, "
                     f"and always ask questions that forces the user to think crtically about the topic at hand. never break character, be socrates himself, that is your personality.")

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # check if user input is in the request form
        if not request.json.get("user_input"):
            flash("User input is required", "error")
            return redirect(f"/chat/{session_id}")

        user_input = request.json.get("user_input")
        chat_history = db.execute("SELECT * FROM messages WHERE session_id = ?", session_id)

        # if there is no chat history, ask the agent to summarize the first message from the user
        if not chat_history:
            summary = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Summarize the following conversation in 5 words based on {user_input} if the input is irrelevant to {selected_subject}, respond with 'irrelevant input': {user_input}"}
                ]
            )

            # if the summary response is "irrelevant input"
            if summary.choices[0].message.content == "irrelevant input":
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Respond with a gentle reminder to stay focused on their studies and ask if they have any questions related to the {selected_subject} since the user input is irrelevant to their studies: {user_input}"}
                    ]
                )
                db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)", session_id, "user", user_input)
                db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)", session_id, "assistant", response.choices[0].message.content)
                flash("Lumen: " + response.choices[0].message.content, "info")
                return redirect(f"/chat/{session_id}")

            # otherwise, insert the summary into the sessions table and continue with the conversation as normal
            else:
                # insert summary into sessions table and user's input and AI response into the messages table with the session_id
                db.execute("UPDATE sessions SET session_summary = ? WHERE id = ?", summary.choices[0].message.content, session_id)
                db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)", session_id, "user", user_input)
                # continue with the conversation as normal and get the AI response based on the user input and system prompt
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_input},
                    ]
                )
                db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)", session_id, "assistant", response.choices[0].message.content)
                flash("Lumen: " + response.choices[0].message.content, "info")
                return redirect(f"/chat/{session_id}")

        # otherwise, when there is chat history, insert the user input and AI response into messages and continue with the conversation as normal
        else:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ]
            )
            db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)", session_id, "user", user_input)
            db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)", session_id, "assistant", response.choices[0].message.content)
            flash("Lumen: " + response.choices[0].message.content, "info")
            return redirect(f"/chat/{session_id}")

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Only greet the user if there is no field in messages table for current session_id
        if not db.execute("SELECT * FROM messages WHERE session_id = ?", session_id):
            username = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]["username"]
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Greet {username} and ask how you can assist them with their studies today."}
                ]
            )
            db.execute("INSERT INTO messages (session_id, role, content) VALUES(?, ?, ?)", session_id, "assistant", response.choices[0].message.content)
            return render_template("chat_interface.html", session_id=session_id, response=response.choices[0].message.content)

        # get chat history from messages table with the session_id and render the chat interface
        else:
            chat_history = db.execute("SELECT * FROM messages WHERE session_id = ?", session_id)
            return render_template("chat_interface.html", session_id=session_id, response=response.choices[0].message.content)


@app.route("/login", methods=["GET", "POST"])
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
            rows[0]["hash"], request.form.get("password")
        ):
            flash("Invalid username or password", "error")
            return render_template("login.html")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
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
            flash("Registration successful! Please setup your account.", "success")
            # Log the user in by remembering their user_id in session
            session["user_id"] = db.execute(
                "SELECT id FROM users WHERE username = ?", request.form.get("username"))[0]["id"]
            return redirect("/setup")
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


@app.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    """ Setup user's account when login for the first time """

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure at least one subject was submitted
        selected_subjects = request.form.getlist("subjects")
        if not selected_subjects:
            flash("Subject is required", "error")
            return render_template("setup.html", subjects=subjects)

        # Insert all the subjects the user selected into the subjects table with the user's id
        for subject in selected_subjects:
            db.execute("INSERT INTO subjects (user_id, subject) VALUES(?, ?)",
                       session["user_id"], subject)

        flash("Account setup successful! You can now start chatting with Lumen.", "success")
        return redirect("/dashboard")

    else:
        # Make sure this is the user's first time logging in by checking subjects table with "user_id"
        rows = db.execute("SELECT subject FROM subjects WHERE user_id = ?", session["user_id"])

        # if there's subjects associated with the user's account
        if rows:
            return redirect("/dashboard")
        # if the query result is empty render the setup page with the list of valid subjects for the user to choose from
        else:
            return render_template("setup.html", subjects=subjects)


@app.route("/dashboard")
@login_required
def dashboard():
    """ Display user stats """

    return redirect("/")
