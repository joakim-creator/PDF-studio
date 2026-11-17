from flask_sqlalchemy import SQLAlchemy

from core.db_routing import TenantSession

db = SQLAlchemy(session_options={'class_': TenantSession})
