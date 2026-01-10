#!/usr/bin/env python3
"""
Initialize test database for stress testing.
Ensures the database has the proper schema before running tests.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment with absolute path
project_dir = Path(__file__).parent.parent
db_path = project_dir / "data" / "test_database.sqlite"
os.environ["DATABASE_URL"] = f"sqlite:///{db_path.absolute()}"

def main():
    """Initialize the test database."""
    
    print("Initializing test database for stress testing...")
    
    # Ensure data directory exists
    data_dir = project_dir / "data"
    data_dir.mkdir(exist_ok=True)
    print(f"Using database: {db_path.absolute()}")
    
    # Import after setting environment
    from app import create_app
    
    try:
        # Create the app (this will initialize the database)
        app = create_app()
        
        with app.app_context():
            from flask_sqlalchemy import SQLAlchemy
            db = app.extensions['sqlalchemy']
            
            # Create all tables
            db.create_all()
            print("✓ Database tables created")
            
            # Verify database works
            result = db.session.execute(db.text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
            tables = [row[0] for row in result]
            print(f"✓ Found {len(tables)} tables: {', '.join(tables)}")
            
        print("✓ Test database initialized successfully")
        return True
        
    except Exception as e:
        print(f"✗ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)