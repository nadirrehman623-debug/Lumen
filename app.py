from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

# Configure application
app = Flask(__name__)


# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")



@app.route("/")
@login_required
def index():
    """ Index/ homepage """

    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    """ Log user in """

    return None


@app.route("/register", methods=["GET", "POST"])
def register():
    """ Register new users """

    return None


@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    """ Log user out """

    return None


@app.route("/Setup", methods=["GET", "POST"])
@login_required
def setup():
    """ Setup user's account when login for the first time """

    return None


@app.route("/dashboard")
@login_required
def dashboard():
    """ Display user stats """

    return None
