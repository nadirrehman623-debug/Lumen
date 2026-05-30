from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

# Configure application
app = Flask(__name__)


# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/login", methods=["GET", "POST"])
def login():
    """ Log user in """

    
