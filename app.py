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
client = OpenAI()

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
            return redirect("/chat")
        else:
            return redirect("/setup")

@app.route("/chat", methods=["GET", "POST"])
@login_required
def chat():
    """ Chat interface for users to interact with the socratic AI asisstant """

    system_prompt = "You are Lumen, a socratic AI assistant designed to help students learn by asking thought-provoking questions. " \
                    "You have access to the user's selected subject for this session, which is " \
                    "Never ever answer user's question directly. make sure to ask questions that guide the user to think critically and arrive at the answer on their own. " \
                    "Always be respectful and encouraging in your responses yet display a socratic personality in your responses. Your goal is to foster a deep understanding of the subject matter and promote independent thinking. " \
                    "The user is a student seeking help with their studies, and you are here to assist them in their learning journey. if the user asks you a question urelated to the current subjects they are studying, " \
                    "respond with a gentle reminder to stay focused on their studies and ask if they have any questions related to the subjects they are studying. also if the user asks you to directly answer their question, " \
                    "respond with a gentle reminder that you are designed to facilitate learning through questioning, not direct answering. " \

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        user_input = request.json.get("user_input")
        # call OpenAI API to generate response based on user input and user's selected subjects. The response should be in JSON format with a "response" key.
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )

        # For now, just render the chat interface. The actual chat functionality will be implemented in a future update.
        flash("Unknown error occurred", "error")
        return redirect("/chat")

    else:
     # For now, just render the chat interface. The actual chat functionality will be implemented in a future update.
        return render_template("chat.html")

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
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)",
                       request.form.get("username"), hash_pass)
            flash("Registration successful! Please setup your account.", "success")
            # Log the user in by remembering their user_id in session
            session["user_id"] = db.execute("SELECT id FROM users WHERE username = ?", request.form.get("username"))[0]["id"]
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
            db.execute("INSERT INTO subjects (user_id, subject) VALUES(?, ?)", session["user_id"], subject)

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
