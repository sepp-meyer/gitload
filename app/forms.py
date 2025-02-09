# app/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from wtforms.validators import DataRequired

class TokenForm(FlaskForm):
    token = StringField('Git Token', validators=[DataRequired()])
    submit = SubmitField('Weiter')

class ProjectForm(FlaskForm):
    project = SelectField('Projekt auswählen', choices=[], validators=[DataRequired()])
    submit = SubmitField('Projekt laden')
