# app/forms.py
from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField
from wtforms.validators import DataRequired

class ProjectForm(FlaskForm):
    project = SelectField('Projekt auswählen', choices=[], validators=[DataRequired()])
    submit = SubmitField('Projekt laden')
