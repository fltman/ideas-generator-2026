import base64
import os
import requests
import json
import uuid
import time
import db  # Import the database module

# Imgur API credentials - store these in environment variables on Replit
IMGUR_CLIENT_ID = os.environ.get('IMGUR_CLIENT_ID', '')
IMGUR_CLIENT_SECRET = os.environ.get('IMGUR_CLIENT_SECRET', '')
IMGUR_API_URL = "https://api.imgur.com/3/image"
IMGUR_OAUTH_URL = "https://api.imgur.com/oauth2/token"

def is_configured():
    """Check if Imgur credentials are configured"""
    return bool(IMGUR_CLIENT_ID)

def initialize_storage():
    """Initialize the database table for Imgur metadata"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Create table for Imgur metadata if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS imgur_metadata (
        image_url TEXT PRIMARY KEY,
        delete_hash TEXT,
        image_id TEXT,
        filename TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        used_oauth BOOLEAN
    )
    ''')
    
    # Create table for OAuth tokens if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS imgur_oauth_tokens (
        id INTEGER PRIMARY KEY,
        access_token TEXT,
        refresh_token TEXT,
        expires_at REAL,
        token_type TEXT,
        account_username TEXT
    )
    ''')
    
    conn.commit()
    conn.close()
    print("Imgur storage tables initialized in database")

# Initialize the tables when the module is imported
try:
    initialize_storage()
except Exception as e:
    print(f"Warning: Could not initialize Imgur storage tables: {str(e)}")

def get_auth_headers():
    """
    Get authorization headers based on available credentials.
    If both client ID and secret are available, try to use OAuth.
    Otherwise, fall back to anonymous upload with client ID only.
    """
    # If we have both client ID and secret, try to use OAuth
    if IMGUR_CLIENT_ID and IMGUR_CLIENT_SECRET:
        token = get_oauth_token()
        if token:
            return {'Authorization': f'Bearer {token}'}
    
    # Fall back to client ID only (anonymous API)
    return {'Authorization': f'Client-ID {IMGUR_CLIENT_ID}'}

def get_oauth_token():
    """
    Get an OAuth token, either from database or by requesting a new one.
    Returns the access token or None if not available.
    """
    if not IMGUR_CLIENT_ID or not IMGUR_CLIENT_SECRET:
        return None
        
    try:
        # Check if we have a cached token in the database
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT access_token, refresh_token, expires_at FROM imgur_oauth_tokens ORDER BY id DESC LIMIT 1")
        token_data = cursor.fetchone()
        conn.close()
        
        if token_data:
            access_token, refresh_token, expires_at = token_data
            
            # Check if token is still valid (with 10 min margin)
            if expires_at > time.time() + 600:
                return access_token
                
            # If we have a refresh token, try to use it
            if refresh_token:
                new_token = refresh_oauth_token(refresh_token)
                if new_token:
                    return new_token
        
        # If we reach here, we need a new token
        return request_new_oauth_token()
        
    except Exception as e:
        print(f"Error getting OAuth token: {str(e)}")
        return None

def save_token_to_db(token_data):
    """Save token data to the database"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Save token to database
        cursor.execute(
            """
            INSERT INTO imgur_oauth_tokens 
            (access_token, refresh_token, expires_at, token_type, account_username) 
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                token_data.get('access_token'),
                token_data.get('refresh_token'),
                token_data.get('expires_at'),
                token_data.get('token_type'),
                token_data.get('account_username')
            )
        )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error saving token to database: {str(e)}")
        return False

def request_new_oauth_token():
    """
    Request a new OAuth token using client credentials grant.
    Returns the access token or None if it fails.
    """
    try:
        data = {
            'client_id': IMGUR_CLIENT_ID,
            'client_secret': IMGUR_CLIENT_SECRET,
            'grant_type': 'client_credentials'
        }
        
        response = requests.post(IMGUR_OAUTH_URL, data=data)
        
        if response.status_code == 200:
            token_data = response.json()
            
            # Calculate expiry time and store token
            expires_at = time.time() + token_data.get('expires_in', 3600)
            token_data['expires_at'] = expires_at
            
            # Save token to database
            save_token_to_db(token_data)
                
            return token_data.get('access_token')
        else:
            print(f"Failed to get OAuth token: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Error requesting OAuth token: {str(e)}")
        return None

def refresh_oauth_token(refresh_token):
    """
    Refresh an OAuth token using a refresh token.
    Returns the new access token or None if it fails.
    """
    try:
        data = {
            'client_id': IMGUR_CLIENT_ID,
            'client_secret': IMGUR_CLIENT_SECRET,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        
        response = requests.post(IMGUR_OAUTH_URL, data=data)
        
        if response.status_code == 200:
            token_data = response.json()
            
            # Calculate expiry time and store token
            expires_at = time.time() + token_data.get('expires_in', 3600)
            token_data['expires_at'] = expires_at
            
            # Save token to database
            save_token_to_db(token_data)
                
            return token_data.get('access_token')
        else:
            print(f"Failed to refresh OAuth token: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Error refreshing OAuth token: {str(e)}")
        return None

def save_image_metadata(image_url, metadata):
    """Save image metadata to the database"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Insert metadata into database
        cursor.execute(
            """
            INSERT INTO imgur_metadata 
            (image_url, delete_hash, image_id, filename, uploaded_at, used_oauth) 
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                image_url,
                metadata.get('deletehash'),
                metadata.get('id'),
                metadata.get('filename'),
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(metadata.get('uploaded_at', time.time()))),
                metadata.get('oauth', False)
            )
        )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error saving image metadata to database: {str(e)}")
        return False

def get_image_metadata(image_url):
    """Get image metadata from the database"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT delete_hash, image_id, filename, used_oauth FROM imgur_metadata WHERE image_url = ?",
            (image_url,)
        )
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            delete_hash, image_id, filename, used_oauth = result
            return {
                'deletehash': delete_hash,
                'id': image_id,
                'filename': filename,
                'oauth': used_oauth
            }
        return None
    except Exception as e:
        print(f"Error getting image metadata from database: {str(e)}")
        return None

def delete_image_metadata(image_url):
    """Delete image metadata from the database"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM imgur_metadata WHERE image_url = ?", (image_url,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    except Exception as e:
        print(f"Error deleting image metadata from database: {str(e)}")
        return False

def save_image_from_base64(base64_string, filename=None):
    """
    Upload a base64 encoded image to Imgur.
    Returns the image URL or None if upload fails.
    """
    if not base64_string:
        return None
        
    if not is_configured():
        print("Imgur not configured: missing CLIENT_ID environment variable")
        return None
        
    try:
        # Handle base64 format variations
        if ',' in base64_string:
            header, base64_string = base64_string.split(',', 1)
            
        # Get authentication headers (will use OAuth if available)
        headers = get_auth_headers()
        
        # Prepare the data for upload
        payload = {
            'image': base64_string,
            'type': 'base64',
            'name': filename or f"image_{uuid.uuid4()}.png",
            'title': 'IdeaSphere Image'
        }
        
        # Upload to Imgur
        response = requests.post(
            IMGUR_API_URL,
            headers=headers,
            data=payload
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                image_data = result.get('data', {})
                image_url = image_data.get('link')
                
                # Store metadata in database
                metadata = {
                    'deletehash': image_data.get('deletehash'),
                    'id': image_data.get('id'),
                    'filename': payload['name'],
                    'uploaded_at': time.time(),
                    'oauth': 'Bearer' in headers.get('Authorization', '')
                }
                
                save_image_metadata(image_url, metadata)
                
                print(f"Image uploaded to Imgur: {image_url}")
                return image_url
            else:
                print(f"Imgur upload error in response: {result}")
                return None
        else:
            print(f"Imgur upload error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Error uploading to Imgur: {str(e)}")
        return None

def get_image_url(image_url):
    """
    Get the URL of an image from Imgur.
    This is a pass-through since we already store the full URL.
    """
    return image_url

def delete_image(image_url):
    """Delete an image from Imgur using the stored metadata"""
    if not image_url or not is_configured():
        return False
        
    try:
        # Get the image metadata from database
        metadata = get_image_metadata(image_url)
        
        if not metadata:
            print(f"No metadata found for {image_url}")
            return False
            
        delete_hash = metadata.get('deletehash')
        image_id = metadata.get('id')
        used_oauth = metadata.get('oauth', False)
        
        # Determine endpoint and headers based on auth method used for upload
        headers = get_auth_headers()
        
        # For authenticated uploads (OAuth), we can use the image ID
        # For anonymous uploads, we must use the deletehash
        if used_oauth and image_id and 'Bearer' in headers.get('Authorization', ''):
            endpoint = f"https://api.imgur.com/3/image/{image_id}"
        elif delete_hash:
            endpoint = f"https://api.imgur.com/3/image/{delete_hash}"
        else:
            print(f"No deletion information available for {image_url}")
            return False
        
        # Delete from Imgur
        response = requests.delete(endpoint, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                # Remove from database
                delete_image_metadata(image_url)
                    
                print(f"Image {image_url} deleted from Imgur")
                return True
                
        print(f"Imgur delete error: {response.status_code} - {response.text}")
        return False
        
    except Exception as e:
        print(f"Error deleting from Imgur: {str(e)}")
        return False

def list_all_images():
    """
    List all image URLs we have stored in the database.
    """
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT image_url FROM imgur_metadata ORDER BY uploaded_at DESC")
        results = cursor.fetchall()
        
        conn.close()
        
        # Extract URLs from results
        return [row[0] for row in results]
        
    except Exception as e:
        print(f"Error listing images from database: {str(e)}")
        return []

def migrate_from_replit_storage():
    """
    Attempt to migrate images from Replit storage to Imgur.
    Returns a dictionary mapping old keys to new Imgur URLs.
    """
    if not is_configured():
        print("Imgur not configured, cannot migrate")
        return {}
        
    migration_map = {}
    
    try:
        # Import the old storage module
        import storage
        print("Attempting to migrate images from Replit storage...")
        
        # Get all images from Replit storage
        replit_images = storage.list_all_images()
        print(f"Found {len(replit_images)} images in Replit storage")
        
        # Migrate each image
        migrated_count = 0
        for image_key in replit_images:
            try:
                # Get image from Replit storage
                image_bytes = storage.client.download_as_bytes(image_key)
                if image_bytes:
                    # Convert to base64
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    
                    # Save to Imgur
                    imgur_url = save_image_from_base64(base64_image, image_key)
                    if imgur_url:
                        migrated_count += 1
                        migration_map[image_key] = imgur_url
                        print(f"Migrated image {image_key} to Imgur: {imgur_url}")
            except Exception as e:
                print(f"Error migrating image {image_key}: {str(e)}")
                
        print(f"Migration complete. Migrated {migrated_count} of {len(replit_images)} images.")
        return migration_map
        
    except Exception as e:
        print(f"Error during migration: {str(e)}")
        return {}

def update_image_urls_in_db(migration_map):
    """
    Update image URLs in the database after migration.
    Takes a dictionary mapping old keys to new Imgur URLs.
    """
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Get all gold ideas with images
        cursor.execute("SELECT id, image_url FROM gold_ideas WHERE image_url IS NOT NULL")
        ideas = cursor.fetchall()
        
        updated_count = 0
        for idea_id, old_image_url in ideas:
            # Extract the image key from the old URL
            # This depends on how you're storing image URLs in your database
            old_key = old_image_url.split('/')[-1] if old_image_url else None
            
            if old_key and old_key in migration_map:
                new_image_url = migration_map[old_key]
                
                # Update the database
                cursor.execute(
                    "UPDATE gold_ideas SET image_url = ? WHERE id = ?",
                    (new_image_url, idea_id)
                )
                updated_count += 1
                print(f"Updated image URL for idea {idea_id}")
                
        conn.commit()
        conn.close()
        
        print(f"Database update complete. Updated {updated_count} ideas.")
        return updated_count
        
    except Exception as e:
        print(f"Error updating database: {str(e)}")
        return 0 