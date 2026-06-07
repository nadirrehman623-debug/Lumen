from flask import redirect, session
from functools import wraps


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
