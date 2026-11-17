from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from core.db_routing import TenantSession

db = SQLAlchemy(session_options={'class_': TenantSession})
login_manager = LoginManager()
csrf = CSRFProtect()
