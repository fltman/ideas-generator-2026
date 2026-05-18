import os
import io
import time
import uuid
import base64
from datetime import datetime
import pytz  # Import pytz for timezone support
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.units import inch
from io import BytesIO
import requests
from PIL import Image as PILImage
import logging
import traceback

# Create a directory for storing PDFs
PDF_DIR = "pdfs"
os.makedirs(PDF_DIR, exist_ok=True)

def create_pdf_for_idea(idea_text, headline, image_url=None):
    """
    Create a PDF for a gold idea and save it to the PDF directory.
    Returns the path to the generated PDF file.
    """
    print(f"Starting PDF generation with headline: {headline}")
    print(f"Image URL provided: {image_url}")
    
    # Generate a unique filename
    timestamp = int(time.time())
    unique_id = str(uuid.uuid4())[:8]
    filename = f"gold_idea_{timestamp}_{unique_id}.pdf"
    filepath = os.path.join(PDF_DIR, filename)
    
    # Create a buffer for the PDF
    buffer = BytesIO()
    
    # Create the PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )
    
    # Create content elements
    styles = getSampleStyleSheet()
    elements = []
    
    # Add a title style
    title_style = styles['Heading1']
    title_style.alignment = 1  # Center alignment
    
    # Add a header with date and time in Stockholm timezone
    stockholm_tz = pytz.timezone('Europe/Stockholm')
    current_datetime = datetime.now(stockholm_tz).strftime("%Y-%m-%d %H:%M:%S")
    elements.append(Paragraph(f"Generated on {current_datetime}", styles['Italic']))
    elements.append(Spacer(1, 0.3*inch))
    
    # Add the headline
    elements.append(Paragraph(headline, title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Add image if available
    if image_url:
        try:
            # Only print a truncated version of the URL, and don't print data URLs at all
            if image_url.startswith('data:image/'):
                print("Processing a data URL image (base64 content)")
            else:
                print(f"Processing image: {image_url[:50]}{'...' if len(image_url) > 50 else ''}")
                
            img_buffer = None
            
            # Handle data URLs (base64 encoded images from storage)
            if image_url.startswith('data:image/'):
                try:
                    # Extract the base64 part
                    _, base64_data = image_url.split(',', 1)
                    img_data = base64.b64decode(base64_data)
                    img = PILImage.open(BytesIO(img_data))
                    print(f"Successfully decoded base64 image: {img.format}, size: {img.size}")
                    img_buffer = BytesIO()
                    img.save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                except Exception as e:
                    print(f"Error processing base64 image: {str(e)}")
                    traceback.print_exc()
            
            # Handle HTTP URLs
            elif image_url.startswith('http'):
                print("Processing as HTTP URL")
                try:
                    response = requests.get(image_url, stream=True, timeout=10)
                    print(f"HTTP response status: {response.status_code}")
                    if response.status_code == 200:
                        img_data = response.content
                        try:
                            img = PILImage.open(BytesIO(img_data))
                            print(f"Successfully downloaded image: {img.format}, size: {img.size}")
                            img_buffer = BytesIO()
                            img.save(img_buffer, format='PNG')
                            img_buffer.seek(0)
                        except Exception as e:
                            print(f"Error processing downloaded image: {str(e)}")
                            traceback.print_exc()
                except Exception as e:
                    print(f"Error downloading image: {str(e)}")
                    traceback.print_exc()
            
            # Handle local file paths
            elif os.path.exists(image_url):
                print(f"Processing as local file: {image_url}")
                try:
                    img = PILImage.open(image_url)
                    print(f"Successfully opened local image: {img.format}, size: {img.size}")
                    img_buffer = BytesIO()
                    img.save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                except Exception as e:
                    print(f"Error processing local image: {str(e)}")
                    traceback.print_exc()
            else:
                print(f"Image URL doesn't match any known format: {image_url[:50]}...")
            
            # If we successfully processed the image, add it to the PDF
            if img_buffer:
                print("Adding image to PDF")
                # Get image dimensions
                img.seek(0) if hasattr(img, 'seek') else None  # Reset to beginning if needed
                img_width, img_height = img.size
                
                # Calculate proper sizing
                max_width = 4 * inch
                max_height = 4 * inch
                aspect = img_height / float(img_width)
                
                if img_width > max_width:
                    img_width = max_width
                    img_height = aspect * img_width
                
                if img_height > max_height:
                    img_height = max_height
                    img_width = img_height / aspect
                
                print(f"Final image dimensions in PDF: {img_width}x{img_height}")
                pdf_img = Image(img_buffer, width=img_width, height=img_height)
                elements.append(pdf_img)
                elements.append(Spacer(1, 0.2*inch))
                print("Image successfully added to PDF elements")
            else:
                print("Failed to process image, no image will be included in PDF")
        except Exception as e:
            print(f"Error adding image to PDF: {str(e)}")
            traceback.print_exc()
    
    # Add the idea text with paragraph formatting
    # Create a larger text style for the idea description
    text_style = ParagraphStyle(
        name='LargerNormal',
        parent=styles['Normal'],
        fontSize=12,  # Increase font size (default is usually 10)
        leading=16    # Increase line spacing
    )
    
    # Split text into paragraphs and add each one
    paragraphs = idea_text.split('\n\n')
    for p in paragraphs:
        if p.strip():
            elements.append(Paragraph(p, text_style))
            elements.append(Spacer(1, 0.1*inch))
    
    # Build the PDF
    try:
        print("Building PDF document")
        doc.build(elements)
        print("PDF built successfully")
        
        # Get the PDF data and save to file
        pdf_data = buffer.getvalue()
        with open(filepath, 'wb') as f:
            f.write(pdf_data)
        
        print(f"PDF saved to: {filepath}")
        return filepath
    except Exception as e:
        print(f"Error building PDF: {str(e)}")
        traceback.print_exc()
        # Still return the path even though it might not exist
        return filepath

def get_oldest_pdf():
    """
    Get the path to the oldest PDF in the queue.
    Returns None if no PDFs are available.
    """
    try:
        pdf_files = [f for f in os.listdir(PDF_DIR) if f.endswith('.pdf')]
        if not pdf_files:
            return None
        
        # Sort files by creation time (oldest first)
        pdf_files.sort(key=lambda f: os.path.getctime(os.path.join(PDF_DIR, f)))
        
        # Return the path to the oldest file
        return os.path.join(PDF_DIR, pdf_files[0])
    except Exception as e:
        print(f"Error getting oldest PDF: {str(e)}")
        return None

def delete_pdf(pdf_path):
    """
    Delete a PDF file from the queue.
    Returns True if successful, False otherwise.
    """
    try:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
            print(f"Deleted PDF: {pdf_path}")
            return True
        return False
    except Exception as e:
        print(f"Error deleting PDF: {str(e)}")
        return False

def count_pdfs():
    """
    Count the number of PDFs in the queue.
    """
    try:
        pdf_files = [f for f in os.listdir(PDF_DIR) if f.endswith('.pdf')]
        return len(pdf_files)
    except Exception as e:
        print(f"Error counting PDFs: {str(e)}")
        return 0 