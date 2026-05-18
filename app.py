import os
from flask import Flask, render_template, jsonify, request, session, make_response, send_file
from chat_request import send_openai_request
import requests
from bs4 import BeautifulSoup
import urllib.parse
import uuid
import db
import json
import time
# Replace the Replit Object Storage with our Imgur storage
import imgur_storage as storage
import base64
from PIL import Image
import io
import pdf_generator  # Import the new PDF generator module

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "default_secret_key")

# Add default settings
DEFAULT_SETTINGS = {
    "openai_api_key": "",
    "openai_model": "openai/gpt-4o-mini",
    "system_prompt": "You are a brilliant inventor that generates ideas.",
    "combination_prompt":
    "Generate 1 possible combination, focusing on how these ideas could work together",
    "generation_prompt": "Generate 3 related ideas for the concept",
}

# Initialize the database when the app starts
with app.app_context():
    db.initialize_db()


# Add migration route to help migrate images from Replit storage to Imgur
@app.route('/admin/migrate-images')
def migrate_images():
    """Admin endpoint to migrate images from Replit storage to Imgur"""
    if not session.get('authenticated'):
        return jsonify({
            "success": False,
            "error": "Authentication required"
        }), 401

    try:
        # Check if Imgur is configured
        if not storage.is_configured():
            return jsonify({
                "success":
                False,
                "error":
                "Imgur not configured. Set IMGUR_CLIENT_ID environment variable."
            }), 500

        # Perform migration
        migration_map = storage.migrate_from_replit_storage()

        # Update database references
        updated_count = storage.update_image_urls_in_db(migration_map)

        return jsonify({
            "success": True,
            "migrated_images": len(migration_map),
            "updated_database_entries": updated_count,
            "migration_map": migration_map
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/')
def index():
    # Ensure the user has a session ID
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

    return render_template('index.html')


@app.route('/authenticate', methods=['POST'])
def authenticate():
    """Authenticate admin password for settings access"""
    password = request.json.get('password')

    if not password:
        return jsonify({"success": False, "error": "Password required"}), 400

    # Verify password against stored password
    authenticated = db.verify_admin_password(password)
    authenticated = True
    if authenticated:
        session['authenticated'] = True
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Invalid password"}), 401


@app.route('/change-password', methods=['POST'])
def change_password():
    """Change the admin password (requires authentication)"""
    # Check if user is authenticated
    if not session.get('authenticated'):
        return jsonify({
            "success": False,
            "error": "Authentication required"
        }), 401

    current_password = request.json.get('current_password')
    new_password = request.json.get('new_password')

    if not current_password or not new_password:
        return jsonify({
            "success": False,
            "error": "Both current and new passwords are required"
        }), 400

    # Verify current password
    if not db.verify_admin_password(current_password):
        return jsonify({
            "success": False,
            "error": "Current password is incorrect"
        }), 401

    # Update password
    success = db.update_admin_password(new_password)

    return jsonify({"success": success})


@app.route('/is-authenticated')
def is_authenticated():
    """Check if the user is authenticated"""
    return jsonify({"authenticated": session.get('authenticated', False)})


@app.route('/logout')
def logout():
    """Remove authentication status"""
    session.pop('authenticated', None)
    return jsonify({"success": True})


@app.route('/update-settings', methods=['POST'])
def update_settings():
    # Check if user is authenticated
    if not session.get('authenticated'):
        return jsonify({
            "success": False,
            "error": "Authentication required"
        }), 401

    settings = request.json
    user_id = session.get('user_id')

    if not user_id:
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id

    success = db.save_user_settings(user_id, settings)

    return jsonify({"success": success})


@app.route('/generate-ideas', methods=['POST'])
def generate_ideas():
    main_idea = request.json.get('idea')
    user_id = session.get('user_id')

    # Get user settings from database or use defaults
    settings = DEFAULT_SETTINGS
    if user_id:
        db_settings = db.get_user_settings(user_id)
        if db_settings:
            settings = db_settings

    if main_idea.startswith('Combine these two ideas:'):
        prompt = f"""Combine these two ideas into one innovative solution.
        {settings['combination_prompt']}.
        {main_idea}
        Respond in JSON format with the following structure:
        {{"ideas": [
            {{"text": "first combined idea"}},
        ]}}"""
    else:
        prompt = f"""{settings['generation_prompt']}: {main_idea}
        Respond in JSON format with the following structure:
        {{"ideas": [
            {{"text": "first related idea"}},
            {{"text": "second related idea"}},
            {{"text": "third related idea"}}
        ]}}"""

    try:
        print(f"Sending prompt: {prompt}")
        # The raw_response parameter is False by default, so it will use JSON format
        response = send_openai_request(prompt, settings.get('system_prompt'),
                                       settings.get('openai_api_key'),
                                       settings.get('openai_model'))
        print(f"Received response: {response}")

        # Get the global rating prompt
        rating_prompt = db.get_rating_prompt()

        # Add the rating prompt to the response
        return jsonify({
            "success": True,
            "data": response,
            "rating_prompt": rating_prompt
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/fetch-url-content', methods=['POST'])
def fetch_url_content():
    data = request.json
    url = data.get('url')

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        headers = {
            'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'

        soup = BeautifulSoup(response.text, 'html.parser')

        # For ComputerSweden, look for specific article content
        article_content = []

        # Get the headline
        headline = soup.find('h1')
        if headline:
            article_content.append(headline.get_text().strip())

        # Get the main article content
        article = soup.find('article')
        if article:
            # Get all text content from the article
            for element in article.find_all(['p', 'h2', 'h3', 'ul', 'ol']):
                # Skip author info, dates, and other metadata
                if not any(skip in element.get_text().lower() for skip in
                           ['av ', 'foto:', 'publicerad:', 'uppdaterad:']):
                    text = element.get_text().strip()
                    if text:
                        article_content.append(text)

        # Join all content with proper spacing
        text = '\n\n'.join(article_content)

        # Clean up text but preserve paragraphs
        text = '\n\n'.join(line.strip() for line in text.split('\n')
                           if line.strip())

        # Increase max length significantly
        max_length = 5000  # Increased from 1000 to 5000
        if len(text) > max_length:
            # Try to cut at the end of a paragraph
            cutoff = text.rfind('\n', 0, max_length)
            if cutoff == -1:
                # If no paragraph break found, try to cut at a sentence
                cutoff = text.rfind('.', 0, max_length)
                if cutoff == -1:
                    cutoff = max_length
            text = text[:cutoff + 1].strip()
            text += '\n\n[...]'  # Add indication that content was truncated

        return jsonify({'content': text})

    except Exception as e:
        print(f"Error fetching URL: {str(e)}")  # Server-side logging
        return jsonify({'error': str(e)}), 500


@app.route('/get-settings')
def get_settings():
    # Check if user is authenticated
    if not session.get('authenticated'):
        return jsonify({
            "success": False,
            "error": "Authentication required",
            "require_auth": True
        }), 401

    user_id = session.get('user_id')

    if not user_id:
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id
        return jsonify(DEFAULT_SETTINGS)

    settings = db.get_user_settings(user_id)
    if not settings:
        return jsonify(DEFAULT_SETTINGS)

    return jsonify(settings)


@app.route('/get-rating-prompt')
def get_rating_prompt():
    """Get the global rating prompt (available to all users)"""
    rating_prompt = db.get_rating_prompt()
    return jsonify({"success": True, "rating_prompt": rating_prompt})


@app.route('/update-rating-prompt', methods=['POST'])
def update_rating_prompt():
    """Update the global rating prompt (requires authentication)"""
    # Check if user is authenticated
    if not session.get('authenticated'):
        return jsonify({
            "success": False,
            "error": "Authentication required"
        }), 401

    data = request.json
    rating_prompt = data.get('rating_prompt')

    if not rating_prompt:
        return jsonify({
            "success": False,
            "error": "Rating prompt is required"
        }), 400

    success = db.update_rating_prompt(rating_prompt)

    if success:
        return jsonify({"success": True})
    else:
        return jsonify({
            "success": False,
            "error": "Failed to update rating prompt"
        }), 500


# New endpoints for prompt groups management


@app.route('/prompt-groups', methods=['GET'])
def get_prompt_groups():
    """Get all prompt groups (available to all users)"""
    groups = db.get_all_prompt_groups()
    return jsonify({"success": True, "prompt_groups": groups})


@app.route('/prompt-groups/<int:group_id>', methods=['GET'])
def get_prompt_group(group_id):
    """Get a specific prompt group details (available to all users)"""
    groups = db.get_all_prompt_groups()
    group = next((g for g in groups if g['id'] == group_id), None)

    if not group:
        return jsonify({
            "success": False,
            "error": "Prompt group not found"
        }), 404

    return jsonify({"success": True, "prompt_group": group})


@app.route('/prompt-groups', methods=['POST'])
def create_prompt_group():
    """Create a new prompt group (requires authentication)"""
    # Check if user is authenticated
    if not session.get('authenticated'):
        return jsonify({
            "success": False,
            "error": "Authentication required"
        }), 401

    data = request.json
    name = data.get('name')
    system_prompt = data.get('system_prompt')
    combination_prompt = data.get('combination_prompt')
    generation_prompt = data.get('generation_prompt')
    is_default = data.get('is_default', False)

    if not name or not system_prompt or not combination_prompt or not generation_prompt:
        return jsonify({
            "success": False,
            "error": "All fields are required"
        }), 400

    group_id = db.create_prompt_group(name, system_prompt, combination_prompt,
                                      generation_prompt, is_default)

    if group_id:
        return jsonify({"success": True, "id": group_id})
    else:
        return jsonify({
            "success": False,
            "error": "Failed to create prompt group"
        }), 500


@app.route('/prompt-groups/<int:group_id>', methods=['PUT'])
def update_prompt_group(group_id):
    """Update an existing prompt group (requires authentication)"""
    # Check if user is authenticated
    if not session.get('authenticated'):
        return jsonify({
            "success": False,
            "error": "Authentication required"
        }), 401

    data = request.json
    name = data.get('name')
    system_prompt = data.get('system_prompt')
    combination_prompt = data.get('combination_prompt')
    generation_prompt = data.get('generation_prompt')
    is_default = data.get('is_default', False)

    if not name or not system_prompt or not combination_prompt or not generation_prompt:
        return jsonify({
            "success": False,
            "error": "All fields are required"
        }), 400

    success = db.update_prompt_group(group_id, name, system_prompt,
                                     combination_prompt, generation_prompt,
                                     is_default)

    if success:
        return jsonify({"success": True})
    else:
        return jsonify({
            "success": False,
            "error": "Failed to update prompt group"
        }), 500


@app.route('/prompt-groups/<int:group_id>', methods=['DELETE'])
def delete_prompt_group(group_id):
    """Delete a prompt group (requires authentication)"""
    # Check if user is authenticated
    if not session.get('authenticated'):
        return jsonify({
            "success": False,
            "error": "Authentication required"
        }), 401

    success = db.delete_prompt_group(group_id)

    if success:
        return jsonify({"success": True})
    else:
        return jsonify({
            "success":
            False,
            "error":
            "Failed to delete prompt group. Note that you cannot delete the default prompt group."
        }), 500


@app.route('/set-prompt-group', methods=['POST'])
def set_user_prompt_group():
    """Set the active prompt group for the current user (available to all users)"""
    user_id = session.get('user_id')

    if not user_id:
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id

    data = request.json
    prompt_group_id = data.get('prompt_group_id')

    # If prompt_group_id is None, just return the current active prompt group
    if prompt_group_id is None:
        # Get the user's current settings
        settings = db.get_user_settings(user_id)
        if settings and 'prompt_group_id' in settings:
            return jsonify({
                "success":
                True,
                "active_prompt_group_id":
                settings['prompt_group_id']
            })
        else:
            # Return default prompt group
            default_group = db.get_default_prompt_group()
            return jsonify({
                "success":
                True,
                "active_prompt_group_id":
                default_group['id'] if default_group else None
            })

    success = db.set_user_prompt_group(user_id, prompt_group_id)

    if success:
        return jsonify({"success": True})
    else:
        return jsonify({
            "success": False,
            "error": "Failed to set prompt group"
        }), 500


@app.route('/get-gold-ideas')
def get_gold_ideas():
    """Get gold-ranked ideas for display"""
    try:
        limit = request.args.get('limit', 1000)
        search = request.args.get('search', None)

        # Debug info
        if search:
            print(f"Searching for gold ideas with query: {search}")

        # Get gold ideas from the database
        gold_ideas = db.get_gold_ideas(int(limit))

        # Filter by search term if provided
        if search and search.strip():
            search = search.lower()
            filtered_ideas = []
            for idea in gold_ideas:
                # Check if search term is in idea text or headline
                if (search in idea['idea_text'].lower()
                        or search in idea['headline'].lower()):
                    filtered_ideas.append(idea)
            gold_ideas = filtered_ideas

            # Debug info
            print(f"Found {len(gold_ideas)} matching ideas after filtering")

        # Return as JSON response
        return jsonify({"success": True, "gold_ideas": gold_ideas})
    except Exception as e:
        print(f"Error getting gold ideas: {str(e)}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/get-image/<path:image_url>')
def get_image(image_url):
    """Redirect to the Imgur image or handle stored image URLs"""
    try:
        # If this is already a full URL, just redirect to it
        if image_url.startswith('http'):
            return jsonify({"success": True, "image_url": image_url})

        # Otherwise, try to get the image from storage
        # This handles the transition period from old storage keys to new URLs
        full_url = storage.get_image_url(image_url)

        if not full_url:
            return jsonify({"success": False, "error": "Image not found"}), 404

        # Return the URL to redirect to
        return jsonify({"success": True, "image_url": full_url})
    except Exception as e:
        print(f"Error in /get-image endpoint: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/gold-ideas', methods=['GET'])
def gold_ideas():
    """Get the list of gold-ranked ideas, with optional search and pagination"""
    # Get search query if provided
    search_query = request.args.get('query', '')

    print(f"Gold ideas endpoint called - search query: '{search_query}'")

    # Always retrieve more ideas than needed to support search filtering
    # and ensure we have enough for pagination
    max_limit = 1000

    # Retrieve gold ideas from database - already sorted by created_at DESC from db.py
    # This will log the first 3 ideas directly from the database
    gold_ideas = db.get_gold_ideas(max_limit)

    print(f"Received {len(gold_ideas)} ideas from database")

    # Handle search if query is provided
    if search_query:
        print(f"Searching for: {search_query}")
        # Since this is a small application, we can do simple filtering in Python
        # For a larger application, this should be done at the database level
        search_query = search_query.lower()
        gold_ideas = [
            idea for idea in gold_ideas
            if search_query in idea['headline'].lower()
            or search_query in idea['idea_text'].lower()
        ]
        print(f"Found {len(gold_ideas)} matching ideas")

    # No need to resort - ideas are already in descending order by date from the database
    if gold_ideas and len(gold_ideas) >= 3:
        print("First 3 ideas being sent to client:")
        for i in range(3):
            idea = gold_ideas[i]
            print(f"  {i+1}. ID: {idea['id']}, Date: {idea['created_at']}")

    return jsonify({"success": True, "gold_ideas": gold_ideas})


def generate_image_for_idea(headline, idea_text, api_key, model="google/gemini-2.5-flash-image-preview"):
    """Generate an image for a gold idea via OpenRouter (Gemini 2.5 Flash Image, aka nano-banana),
    save it to Imgur and return the image URL plus the original base64 payload."""
    if not api_key:
        print("No OpenRouter API key provided for image generation")
        return None, None

    try:
        prompt = f"Create a beautiful, professional, high-quality illustration for the following concept: {headline}. {idea_text[:200]}..."

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "http://localhost"),
            "X-Title": os.environ.get("OPENROUTER_APP_TITLE", "IdeaSphere Kronoberg"),
        }

        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"],
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            data=json.dumps(data))

        if response.status_code != 200:
            print(f"Error generating image: {response.status_code} - {response.text}")
            return None, None

        result = response.json()
        images = (result.get("choices", [{}])[0]
                        .get("message", {})
                        .get("images") or [])
        if not images:
            print(f"No image data returned from OpenRouter: {result}")
            return None, None

        image_url_field = images[0].get("image_url", {}).get("url", "")
        if image_url_field.startswith("data:"):
            # data:image/png;base64,XXXX  ->  XXXX
            base64_image = image_url_field.split(",", 1)[1]
        else:
            base64_image = image_url_field

        timestamp = int(time.time())
        unique_id = str(uuid.uuid4())[:8]
        filename = f"gold_idea_{timestamp}_{unique_id}.png"

        image_url = storage.save_image_from_base64(base64_image, filename)

        if image_url:
            print(f"Image saved to Imgur: {image_url}")
            return image_url, base64_image
        else:
            print("Failed to save image to Imgur")
            return None, base64_image

    except Exception as e:
        print(f"Exception during image generation: {str(e)}")
        return None, None


@app.route('/rate-idea', methods=['POST'])
def rate_idea():
    """Use AI to rate an idea based on the rating prompt"""
    idea_text = request.json.get('idea_text')
    user_id = session.get('user_id')

    if not idea_text:
        return jsonify({
            "success": False,
            "error": "Idea text is required"
        }), 400

    # Get user settings from database or use defaults
    settings = DEFAULT_SETTINGS
    if user_id:
        db_settings = db.get_user_settings(user_id)
        if db_settings:
            settings = db_settings

    # Get the rating prompt from database
    rating_prompt = db.get_rating_prompt()

    # Create prompt for the AI rating - only use the custom rating prompt
    prompt = f"""
    {rating_prompt}
    
    Idea: {idea_text}
    
    Make sure to respond with ONLY a single number (0, 1, 2, or 3) representing your rating.
    Do not format as JSON.
    """

    try:
        print(f"Sending rating prompt: {prompt}")

        # Use the raw_response parameter to indicate we want text, not JSON
        response = send_openai_request(
            prompt,
            settings.get('system_prompt'),
            settings.get('openai_api_key'),
            settings.get('openai_model'),
            raw_response=True  # Add this parameter to get text response
        )

        print(f"Received rating response: {response}")

        # Extract the numerical rating (0-3) from the response
        response_text = response.strip()
        rating = 0

        # Try to extract a single digit (0-3) from the response
        import re
        match = re.search(r'[0-3]', response_text)
        if match:
            rating = int(match.group(0))

        # If the idea received a gold rating (3 stars), generate a headline and save it
        if rating == 3:
            # Generate headline using OpenAI
            headline_prompt = f"""
            Create a short, catchy headline (maximum 8 words) for the following idea:
            
            {idea_text}
            
            IMPORTANT: The headline MUST be in the same language as the original idea.
            The headline should be compelling and capture the essence of the idea.
            Respond with ONLY the headline text.
            """

            try:
                headline_response = send_openai_request(
                    headline_prompt,
                    "You are a creative headline writer. Create short, memorable headlines in the same language as the provided idea.",
                    settings.get('openai_api_key'),
                    settings.get('openai_model'),
                    raw_response=True)

                # Clean up the headline (remove quotes, newlines, etc.)
                headline = headline_response.strip().strip('"\'').strip()

                # Generate an image for the idea if API key is available
                image_key = None
                original_base64_image = None
                if settings.get('openai_api_key'):
                    image_key, original_base64_image = generate_image_for_idea(
                        headline, idea_text, settings.get('openai_api_key'))

                    if image_key:
                        print(f"Generated image key: {image_key}")
                    else:
                        print("No image key was generated")

                    if original_base64_image:
                        print(
                            f"Original base64 image data received (length: {len(original_base64_image)} bytes)"
                        )
                    else:
                        print("No original base64 image data received")

                # Save the gold idea to the database with image URL/key
                idea_id = db.save_gold_idea(idea_text, headline, image_key)

                print(
                    f"Saved gold idea with headline: {headline} and image key: {image_key}"
                )

                # Use the original base64 image data for PDF generation if available
                pdf_image_url = None

                if original_base64_image:
                    # Create data URL from original base64 data
                    pdf_image_url = f"data:image/png;base64,{original_base64_image}"
                    print(
                        "Using original base64 image data for PDF generation")
                elif image_key:
                    # Fallback: Try to get the image URL from storage
                    try:
                        pdf_image_url = storage.get_image_url(image_key)
                        print(
                            "Using image URL from storage for PDF generation")
                    except Exception as e:
                        print(
                            f"Error getting image URL from storage: {str(e)}")

                # Final fallback: Use a reliable direct Imgur URL
                if not pdf_image_url and image_key and (
                        'imgur.com' in image_key.lower()
                        or image_key.startswith('https://i.')):
                    pdf_image_url = image_key
                    print(
                        f"Using direct Imgur URL for PDF generation: {pdf_image_url}"
                    )

                # Generate a PDF for printing
                try:
                    # Don't print the actual URL if it's a data URL
                    if pdf_image_url and pdf_image_url.startswith('data:'):
                        print("Creating PDF with data URL image")
                    else:
                        print(
                            f"Creating PDF with image URL type: {'none' if not pdf_image_url else 'imgur' if 'imgur.com' in pdf_image_url else 'http' if pdf_image_url.startswith('http') else 'unknown'}"
                        )

                    pdf_path = pdf_generator.create_pdf_for_idea(
                        idea_text, headline, pdf_image_url)
                    print(f"Generated PDF for printing: {pdf_path}")
                except Exception as e:
                    print(f"Error generating PDF: {str(e)}")

            except Exception as e:
                print(f"Error generating headline or image: {str(e)}")
                import traceback
                traceback.print_exc()

        return jsonify({"success": True, "rating": rating})
    except Exception as e:
        print(f"Error rating idea: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/gold-ideas-page')
def gold_ideas_page():
    """Render the gold ideas page"""
    return render_template('gold_ideas.html')


@app.route('/debug-gold-ideas', methods=['GET'])
def debug_gold_ideas():
    """Debug endpoint that returns gold ideas in raw format"""
    # Retrieve gold ideas from database
    gold_ideas = db.get_gold_ideas(1000)

    # Create a simple list with just ID, headline and date plus image info for debugging
    debug_ideas = []
    for idea in gold_ideas:
        # Determine image type
        image_type = "none"
        if idea["image_url"]:
            if idea["image_url"].startswith("/static/"):
                image_type = "local"
            elif idea["image_url"].startswith("http"):
                image_type = "external"
            else:
                image_type = "unknown"

        debug_ideas.append({
            "id":
            idea["id"],
            "headline":
            idea["headline"][:30] + "..." if idea["headline"]
            and len(idea["headline"]) > 30 else idea["headline"],
            "has_image":
            idea["image_url"] is not None,
            "image_type":
            image_type,
            "image_url_preview":
            idea["image_url"][:40] + "..." if idea["image_url"]
            and len(idea["image_url"]) > 40 else idea["image_url"],
            "created_at":
            idea["created_at"]
        })

    return jsonify({
        "success": True,
        "message":
        "This is a debug endpoint that shows ideas in raw format as returned from the database",
        "count": len(debug_ideas),
        "order": "Should be newest first (DESC by created_at)",
        "ideas": debug_ideas
    })


@app.route('/debug-image-test')
def debug_image_test():
    """Debug endpoint to test image storage and retrieval"""
    try:
        # Create a simple test image (a red square)
        img = Image.new('RGB', (100, 100), color='red')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)

        # Convert to base64
        test_image_base64 = base64.b64encode(
            img_byte_arr.read()).decode('utf-8')

        # Save the test image to storage
        image_key = storage.save_image_from_base64(test_image_base64,
                                                   "test_image.png")

        if not image_key:
            return jsonify({
                "success": False,
                "error": "Failed to save test image to storage"
            })

        # List all images in storage
        all_images = storage.list_all_images()

        # Try to retrieve the image
        image_url = storage.get_image_url(image_key)

        return jsonify({
            "success": True,
            "test_complete": True,
            "image_key": image_key,
            "image_exists_in_list": image_key in all_images,
            "image_retrieval_success": image_url is not None,
            "all_images": all_images,
            "debug_info": {
                "using_replit": storage.USING_REPLIT,
                "image_url_length": len(image_url) if image_url else 0
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/debug-storage')
def debug_storage():
    """Debug endpoint to inspect Imgur storage state"""
    try:
        # Get database connection
        conn = db.get_db_connection()
        cursor = conn.cursor()

        # Get all tables in the database
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        # Get all stored images from Imgur metadata table
        all_images = []
        if 'imgur_metadata' in tables:
            cursor.execute(
                "SELECT image_url, delete_hash, image_id, filename, uploaded_at, used_oauth FROM imgur_metadata ORDER BY uploaded_at DESC"
            )
            rows = cursor.fetchall()

            for row in rows:
                image_url, delete_hash, image_id, filename, uploaded_at, used_oauth = row
                all_images.append({
                    "url": image_url,
                    "id": image_id,
                    "filename": filename,
                    "uploaded_at": uploaded_at,
                    "used_oauth": used_oauth,
                    "has_delete_hash": delete_hash is not None
                })

        # Get OAuth token info if available
        oauth_info = None
        if 'imgur_oauth_tokens' in tables:
            cursor.execute(
                "SELECT access_token, refresh_token, expires_at, token_type FROM imgur_oauth_tokens ORDER BY id DESC LIMIT 1"
            )
            token_row = cursor.fetchone()

            if token_row:
                access_token, refresh_token, expires_at, token_type = token_row
                oauth_info = {
                    "token_type": token_type,
                    "expires_at": expires_at,
                    "time_remaining":
                    expires_at - time.time() if expires_at else None,
                    "has_access_token": access_token is not None,
                    "has_refresh_token": refresh_token is not None
                }

        conn.close()

        # Check if credentials are configured
        imgur_configured = storage.is_configured()
        client_id = storage.IMGUR_CLIENT_ID
        client_secret = storage.IMGUR_CLIENT_SECRET

        return jsonify({
            "success": True,
            "imgur_configured": imgur_configured,
            "client_id_available": bool(client_id),
            "client_secret_available": bool(client_secret),
            "database_tables": tables,
            "total_images": len(all_images),
            "sample_images": all_images[:5],  # Show first 5 images
            "oauth_info": oauth_info
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/debug-imgur-test')
def debug_imgur_test():
    """Debug endpoint to test Imgur image storage"""
    try:
        # Check if Imgur is configured
        if not storage.is_configured():
            return jsonify({
                "success":
                False,
                "error":
                "Imgur not configured. Set IMGUR_CLIENT_ID environment variable."
            }), 500

        # Get authentication info
        using_oauth = bool(storage.IMGUR_CLIENT_SECRET)
        oauth_token = storage.get_oauth_token() if using_oauth else None

        # Create a simple test image (a red square)
        img = Image.new('RGB', (100, 100), color='red')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)

        # Convert to base64
        test_image_base64 = base64.b64encode(
            img_byte_arr.read()).decode('utf-8')

        # Save the test image to Imgur
        image_url = storage.save_image_from_base64(test_image_base64,
                                                   "test_image.png")

        if not image_url:
            return jsonify({
                "success": False,
                "error": "Failed to save test image to Imgur"
            })

        # Try to retrieve the image URL
        retrieved_url = storage.get_image_url(image_url)

        # Check if metadata was saved properly
        metadata = storage.get_image_metadata(image_url)

        # Get a list of all images
        all_images = storage.list_all_images()

        # Get connection to check if tables exist
        conn = db.get_db_connection()
        cursor = conn.cursor()

        # Check if the Imgur tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND (name='imgur_metadata' OR name='imgur_oauth_tokens')"
        )
        tables = [row[0] for row in cursor.fetchall()]

        # Count the total number of images
        cursor.execute("SELECT COUNT(*) FROM imgur_metadata")
        total_count = cursor.fetchone()[0]

        conn.close()

        return jsonify({
            "success":
            True,
            "test_complete":
            True,
            "image_url":
            image_url,
            "retrieved_url":
            retrieved_url,
            "imgur_configured":
            storage.is_configured(),
            "client_id_available":
            bool(storage.IMGUR_CLIENT_ID),
            "client_secret_available":
            bool(storage.IMGUR_CLIENT_SECRET),
            "using_oauth":
            using_oauth,
            "oauth_token_available":
            oauth_token is not None,
            "metadata_saved":
            metadata is not None,
            "image_url_matches":
            image_url == retrieved_url,
            "total_images":
            total_count,
            "database_tables":
            tables,
            "sample_images":
            all_images[:5] if all_images else []
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/download-next-pdf')
def download_next_pdf():
    """Download the oldest PDF in the queue and then delete it"""
    try:
        # Get the path to the oldest PDF
        pdf_path = pdf_generator.get_oldest_pdf()

        if not pdf_path:
            return jsonify({
                "success": False,
                "error": "No PDFs available for printing"
            }), 404

        # Read the PDF file into memory
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()

        # Delete the file immediately after reading it
        success = pdf_generator.delete_pdf(pdf_path)
        if success:
            print(f"PDF deleted after reading into memory: {pdf_path}")
        else:
            print(f"Warning: Failed to delete PDF file: {pdf_path}")

        # Get the filename
        filename = os.path.basename(pdf_path)

        # Create a response with the PDF data
        response = make_response(pdf_data)
        response.headers.set('Content-Type', 'application/pdf')
        response.headers.set('Content-Disposition',
                             f'attachment; filename="{filename}"')

        return response

    except Exception as e:
        print(f"Error downloading PDF: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/pdf-queue-status')
def pdf_queue_status():
    """Get status information about the PDF queue"""
    try:
        count = pdf_generator.count_pdfs()
        return jsonify({"success": True, "pdfs_in_queue": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/debug-pdf-generation')
def debug_pdf_generation():
    """Debug endpoint to manually generate a test PDF and add it to the queue"""
    try:
        # Create a test idea
        idea_text = "This is a test idea with multiple paragraphs.\n\n" + \
                     "It includes line breaks and formatting to test the PDF generation.\n\n" + \
                     "The PDF should properly format this text with paragraphs and spacing."

        headline = "Test PDF Generation"

        # Test different image types
        image_type = request.args.get('image_type', 'imgur')
        print(f"Debug PDF generation with image type: {image_type}")

        if image_type == 'imgur':
            # Use Imgur URL that's known to work in this environment
            image_url = "https://i.imgur.com/JfkNT5r.jpeg"
            print(f"Using Imgur image URL: {image_url}")
        elif image_type == 'custom':
            # Use a custom URL provided in the request
            custom_url = request.args.get('url',
                                          'https://i.imgur.com/JfkNT5r.jpeg')
            image_url = custom_url
            print(f"Using custom image URL: {image_url}")
        elif image_type == 'placeholder':
            # Create a test image URL - using a placeholder image (may not work in all environments)
            image_url = "https://via.placeholder.com/800x600.png?text=Test+Image"
        elif image_type == 'local':
            # Try to use a local test image if available
            test_image_path = os.path.join('static', 'images',
                                           'test_image.png')
            if not os.path.exists(os.path.dirname(test_image_path)):
                os.makedirs(os.path.dirname(test_image_path), exist_ok=True)

            # If test image doesn't exist, create a simple one
            if not os.path.exists(test_image_path):
                try:
                    from PIL import Image, ImageDraw, ImageFont
                    img = Image.new('RGB', (800, 600), color='blue')
                    draw = ImageDraw.Draw(img)
                    draw.rectangle([(200, 150), (600, 450)], fill='white')
                    draw.text((300, 300), "Test Image", fill='black')
                    img.save(test_image_path)
                    print(f"Created test image at {test_image_path}")
                except Exception as e:
                    print(f"Error creating test image: {str(e)}")
                    # Fall back to Imgur
                    image_url = "https://i.imgur.com/JfkNT5r.jpeg"

            image_url = test_image_path
        elif image_type == 'base64':
            # Create a simple base64 encoded image
            try:
                from PIL import Image, ImageDraw
                import base64
                import io

                # Create a simple image
                img = Image.new('RGB', (800, 600), color='green')
                draw = ImageDraw.Draw(img)
                draw.rectangle([(200, 150), (600, 450)], fill='yellow')
                draw.ellipse([(300, 200), (500, 400)], fill='red')

                # Convert to base64
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                buffer.seek(0)
                base64_data = base64.b64encode(
                    buffer.getvalue()).decode('utf-8')
                image_url = f"data:image/png;base64,{base64_data}"
                print(f"Created base64 image (size: {len(base64_data)} bytes)")
            except Exception as e:
                print(f"Error creating base64 image: {str(e)}")
                # Fall back to Imgur
                image_url = "https://i.imgur.com/JfkNT5r.jpeg"
        else:
            # Default to Imgur
            image_url = "https://i.imgur.com/JfkNT5r.jpeg"

        print(
            f"Using image URL: {image_url[:100]}{'...' if len(image_url) > 100 else ''}"
        )

        # Generate the PDF
        pdf_path = pdf_generator.create_pdf_for_idea(idea_text, headline,
                                                     image_url)

        # Verify PDF was created
        pdf_exists = os.path.exists(pdf_path) if pdf_path else False

        # Count PDFs in queue
        count = pdf_generator.count_pdfs()

        return jsonify({
            "success": True,
            "message": "Test PDF generation complete",
            "pdf_path": pdf_path,
            "pdf_exists": pdf_exists,
            "pdfs_in_queue": count,
            "image_type_used": image_type,
            "debug_info": {
                "headline":
                headline,
                "image_url_type":
                "base64" if image_type == 'base64' else
                ("local_file" if image_type == 'local' else
                 ("imgur" if image_url.startswith('https://i.imgur.com') else
                  ("http_url" if image_url.startswith('http') else "unknown")))
            }
        })
    except Exception as e:
        import traceback
        print(f"Error in debug PDF generation: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
