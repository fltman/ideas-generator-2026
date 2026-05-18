import db
import uuid

def test_db_connection():
    """Test database initialization and basic operations"""
    try:
        # Initialize the database (creates tables)
        db.initialize_db()
        print("✅ Database initialized successfully")
        
        # Generate a test session ID
        test_session_id = str(uuid.uuid4())
        print(f"Test session ID: {test_session_id}")
        
        # Create test settings
        test_settings = {
            "openai_api_key": "test-key",
            "openai_model": "test-model",
            "system_prompt": "Test system prompt",
            "combination_prompt": "Test combination prompt",
            "generation_prompt": "Test generation prompt"
        }
        
        # Save settings
        success = db.save_user_settings(test_session_id, test_settings)
        if success:
            print("✅ Settings saved successfully")
        else:
            print("❌ Failed to save settings")
            return
        
        # Retrieve settings
        retrieved_settings = db.get_user_settings(test_session_id)
        if retrieved_settings:
            print("✅ Settings retrieved successfully")
            print("Retrieved settings:")
            for key, value in retrieved_settings.items():
                print(f"  {key}: {value}")
                
            # Verify settings
            all_match = True
            for key in test_settings:
                if test_settings[key] != retrieved_settings[key]:
                    all_match = False
                    print(f"❌ Mismatch for {key}:")
                    print(f"  Expected: {test_settings[key]}")
                    print(f"  Got: {retrieved_settings[key]}")
            
            if all_match:
                print("✅ All settings match")
            
        else:
            print("❌ Failed to retrieve settings")
            
        print("\nTest completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")

if __name__ == "__main__":
    test_db_connection() 