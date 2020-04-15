import click
from flask import Flask
from flask.cli import FlaskGroup

import manuka


@click.group(cls=FlaskGroup, create_app=manuka.create_app)
def cli():
    """Management script for the Manuka application."""
