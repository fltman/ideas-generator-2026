import db

def test_auth_functionality():
    """Test authentication functionality"""
    try:
        # Initialize database (creates tables and default password)
        db.initialize_db()
        print("✅ Database initialized successfully")
        
        # 1. Test default password authentication
        result = db.verify_admin_password(db.DEFAULT_ADMIN_PASSWORD)
        if result:
            print(f"✅ Default password authentication successful")
        else:
            print(f"❌ Default password authentication failed")
            
        # 2. Test wrong password
        result = db.verify_admin_password("wrong_password")
        if not result:
            print(f"✅ Wrong password rejection successful")
        else:
            print(f"❌ Wrong password rejection failed")
            
        # 3. Test password change
        new_password = "new_test_password"
        success = db.update_admin_password(new_password)
        if success:
            print(f"✅ Password update successful")
        else:
            print(f"❌ Password update failed")
            return
            
        # 4. Test authentication with new password
        result = db.verify_admin_password(new_password)
        if result:
            print(f"✅ New password authentication successful")
        else:
            print(f"❌ New password authentication failed")
            
        # 5. Test that old password no longer works
        result = db.verify_admin_password(db.DEFAULT_ADMIN_PASSWORD)
        if not result:
            print(f"✅ Old password rejection successful")
        else:
            print(f"❌ Old password still works, rejection failed")
            
        # 6. Reset to default password for convenience
        success = db.update_admin_password(db.DEFAULT_ADMIN_PASSWORD)
        if success:
            print(f"✅ Reset to default password successful")
        else:
            print(f"❌ Reset to default password failed")
            
        print("\nAuthentation testing completed successfully!")
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")

if __name__ == "__main__":
    test_auth_functionality() 