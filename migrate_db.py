import db
import psycopg2

def migrate_db():
    """Apply database migrations to update the schema"""
    conn = None
    try:
        # Get a connection from the pool
        conn = db.connection_pool.getconn()
        cur = conn.cursor()
        
        print("Starting database migration...")
        
        # Check if the active_prompt_group_id column exists in user_settings table
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'user_settings' 
            AND column_name = 'active_prompt_group_id'
        """)
        
        column_exists = cur.fetchone() is not None
        
        if not column_exists:
            print("Adding active_prompt_group_id column to user_settings table...")
            cur.execute("""
                ALTER TABLE user_settings 
                ADD COLUMN active_prompt_group_id INTEGER
            """)
            print("Column added successfully.")
            
            # Optional: Add a foreign key constraint if needed
            cur.execute("""
                ALTER TABLE user_settings
                ADD CONSTRAINT fk_prompt_group
                FOREIGN KEY (active_prompt_group_id)
                REFERENCES prompt_groups(id)
                ON DELETE SET NULL
            """)
            print("Foreign key constraint added.")
            
            conn.commit()
            print("Migration completed successfully.")
        else:
            print("Column active_prompt_group_id already exists, no migration needed.")
        
    except Exception as e:
        print(f"Error during migration: {str(e)}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            db.connection_pool.putconn(conn)

if __name__ == "__main__":
    migrate_db() 