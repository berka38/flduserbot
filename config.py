import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Language settings
    LANGUAGES = ['en', 'tr'] # Desteklenen diller
    BABEL_DEFAULT_LOCALE = 'en' # Varsayılan dil
    BABEL_TRANSLATION_DIRECTORIES = os.path.join(basedir, 'app', 'translations') # Çeviri dosyalarının konumu

    # Pending logins cache (simple in-memory)
    # In production, consider using Redis or another persistent cache
    PENDING_LOGINS = {} # { account_id: { ... data ... } }
    # Dictionary to keep track of running bot processes
    RUNNING_BOTS = {} # { account_id: subprocess.Popen object } 