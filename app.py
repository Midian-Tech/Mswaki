from flask import Flask, render_template, redirect

def create_app():
    app = Flask(__name__)
    
    # --- Add this route ---
    @app.route("/")
    def home():
        # Option 1: redirect to dashboard route
        return redirect("/user_dashboard")

        # Option 2: render a template
        # return render_template("user_dashboard.html")
    
    # other app setup, blueprints, etc.
    
    return app
