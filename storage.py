import io
import os
import base64
import uuid
from PIL import Image
import json
import os.path

# Försök importera Replit Object Storage, men ha en fallback om det inte går
try:
    from replit.object_storage import Client
    client = Client()
    USING_REPLIT = True
    print("Using Replit Object Storage for image storage")
except ImportError:
    # Om Replit inte är tillgängligt, skapa en mockad version som använder lokal lagring
    USING_REPLIT = False
    print(
        "Replit Object Storage not available, using local file storage for images"
    )

    # Skapa en lokal mapp för bilder om den inte finns
    LOCAL_STORAGE_DIR = os.path.join('static', 'images', 'storage')
    os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)

    # Mockad version av Replit Client
    class MockClient:

        def __init__(self):
            self.storage_dir = LOCAL_STORAGE_DIR
            # Cache av fillistning för att förbättra prestanda
            self._files_cache = None
            self._last_cache_update = 0

        def list(self):
            # Uppdatera cachen om det behövs
            import time
            current_time = time.time()
            if self._files_cache is None or current_time - self._last_cache_update > 5:  # 5 sekunder cache
                self._files_cache = [
                    f for f in os.listdir(self.storage_dir)
                    if os.path.isfile(os.path.join(self.storage_dir, f))
                ]
                self._last_cache_update = current_time
            return self._files_cache

        def upload_from_bytes(self, filename, data):
            filepath = os.path.join(self.storage_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(data)
            # Uppdatera cachen
            if self._files_cache is not None:
                self._files_cache.append(filename)
            return True

        def download_as_bytes(self, filename):
            filepath = os.path.join(self.storage_dir, filename)
            if not os.path.exists(filepath):
                return None
            with open(filepath, 'rb') as f:
                return f.read()

        def delete(self, filename):
            filepath = os.path.join(self.storage_dir, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                # Uppdatera cachen
                if self._files_cache is not None and filename in self._files_cache:
                    self._files_cache.remove(filename)
                return True
            return False

    # Använd den mockade versionen
    client = MockClient()


def save_image_from_base64(base64_string, filename=None):
    """
    Spara en base64-kodad bild till lagring (Replit Object Storage eller lokalt).
    Returnerar bild-URL:en (namnet på objektet i lagringen).
    """
    if not base64_string:
        return None

    try:
        # Hantera olika format på base64-strängen
        if ',' in base64_string:
            header, base64_string = base64_string.split(',', 1)

        # Konvertera base64 till bytes
        image_data = base64.b64decode(base64_string)

        # Generera ett unikt filnamn om inget angivits
        if not filename:
            # Använd UUID för att generera unika filnamn
            filename = f"image_{uuid.uuid4()}.png"

        # Ladda upp bilden
        client.upload_from_bytes(filename, image_data)

        print(f"Image saved as {filename}")
        return filename

    except Exception as e:
        print(f"Error saving image: {str(e)}")
        return None


def get_image_url(image_key):
    """
    Hämtar en bild från Replit Object Storage som base64-sträng.
    """
    if not image_key:
        return None

    try:
        print(f"Attempting to download image: {image_key}")
        
        # List all storage objects for debugging
        all_objects = client.list()
        print(f"All objects in storage: {all_objects}")
        print(f"Image key exists in list: {image_key in all_objects}")
        
        # Get exact object names for comparison
        similar_keys = [name for name in all_objects if image_key in name]
        if similar_keys:
            print(f"Found similar keys: {similar_keys}")
        
        # Hämta bilden som bytes
        image_bytes = client.download_as_bytes(image_key)
        
        if not image_bytes:
            print(f"Error: Image not found or empty: {image_key}")
            return None

        print(f"Successfully downloaded {len(image_bytes)} bytes")
            
        # Konvertera till base64
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        # Bestäm MIME-typen baserat på filnamnets ändelse
        mime_type = "image/png"  # Standard
        if image_key.lower().endswith('.jpg') or image_key.lower().endswith('.jpeg'):
            mime_type = "image/jpeg"
        elif image_key.lower().endswith('.gif'):
            mime_type = "image/gif"
        elif image_key.lower().endswith('.webp'):
            mime_type = "image/webp"

        return f"data:{mime_type};base64,{base64_image}"

    except Exception as e:
        print(f"Error retrieving image from storage: {str(e)}")
        return None


def delete_image(image_key):
    """
    Ta bort en bild från lagringen.
    """
    if not image_key:
        return False

    try:
        if image_key in client.list():
            client.delete(image_key)
            print(f"Image {image_key} deleted")
            return True
        return False
    except Exception as e:
        print(f"Error deleting image: {str(e)}")
        return False


def list_all_images():
    """
    Listar alla bilder i lagringen.
    """
    try:
        return client.list()
    except Exception as e:
        print(f"Error listing images: {str(e)}")
        return []
