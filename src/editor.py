"""Metadata Editor module for parsing, validating, saving, and writing metadata.

Provides functions to parse metadata text from the editor, validate changes,
update database records, and write metadata back to various file types.
Supports PDF, images (PNG/JPEG), audio (MP3), and text files.
"""

import json
import re
from datetime import datetime
import db
import os
import shutil


class MetadataEditor:
    """Object-oriented metadata editor with parsing, validation, and file writing capabilities."""

    def __init__(self, db_client: db.MetadataDatabase | None = None) -> None:
        self.db_client = db_client or db.db_manager

    def parse_editor_text(self, text: str) -> dict:
        """Parse metadata text from editor into structured data.
        
        Separates standard headers (File Name, File Size, etc.) from custom metadata.
        
        Args:
            text (str): Raw text from editor containing key:value pairs.
            
        Returns:
            dict: Dictionary with 'headers' and 'metadata' keys containing parsed data.
        """
        lines = text.strip().split('\n')
        headers = {}
        metadata = {}

        for line in lines:
            line = line.strip()
            if not line or ':' not in line:
                continue

            parts = line.split(':', 1)
            if len(parts) != 2:
                continue

            key = parts[0].strip()
            value = parts[1].strip()

            if key in ['File Name', 'File Size', 'File Type', 'Extracted At', 'Modified On']:
                headers[key] = value
            else:
                metadata[key] = value

        return {'headers': headers, 'metadata': metadata}

    def validate_metadata(self, parsed_data: dict) -> tuple[bool, str]:
        """Validate parsed metadata for required fields and format.
        
        Args:
            parsed_data (dict): Parsed metadata dictionary with 'headers' and 'metadata' keys.
            
        Returns:
            tuple: (is_valid, error_message)
        """
        headers = parsed_data.get('headers', {})

        required = ['File Name']
        for field in required:
            if field not in headers or not headers[field]:
                return False, f"Missing required field: {field}"

        if not parsed_data.get('metadata'):
            return False, "Metadata cannot be empty"

        return True, ""

    def save_edited_metadata(self, file_path: str, parsed_data: dict) -> tuple[bool, str]:
        """Save edited metadata back to the database.
        
        Args:
            file_path (str): Path to the original file.
            parsed_data (dict): Parsed and validated metadata dictionary.
            
        Returns:
            tuple: (success, message) - Boolean status and informational message.
        """
        try:
            valid, error = self.validate_metadata(parsed_data)
            if not valid:
                return False, error

            latest = self.db_client.fetch_latest_by_path(file_path)
            if not latest:
                return False, "No existing record found for this file"

            updated_metadata = parsed_data['metadata']

            import sqlite3
            with sqlite3.connect(self.db_client.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE metadata 
                    SET full_metadata = ?
                    WHERE id = ?
                ''', (json.dumps(updated_metadata), latest[0]))
                conn.commit()

            return True, "Metadata updated successfully"

        except Exception as e:
            return False, f"Error saving metadata: {str(e)}"

    def get_editable_text(self, file_path: str, metadata: dict) -> str:
        """Build editable text format from file path and metadata dict.
        
        Creates a formatted text representation of metadata with headers and custom fields.
        
        Args:
            file_path (str): Path to the file.
            metadata (dict): Metadata dictionary to format.
            
        Returns:
            str: Formatted text for display in editor.
        """
        lines = []

        try:
            latest = self.db_client.fetch_latest_by_path(file_path)
        except Exception:
            latest = None

        def _fmt(dt_str):
            if not dt_str:
                return ""
            try:
                return datetime.fromisoformat(dt_str).strftime("%b %d, %Y %I:%M %p")
            except Exception:
                return dt_str

        file_name = os.path.basename(file_path)
        if latest:
            size_fmt = latest[3]
            ftype = latest[4]
            extracted_at_h = _fmt(latest[5])
            modified_on_h = _fmt(latest[6])
        else:
            try:
                size_bytes = os.path.getsize(file_path)
            except Exception:
                size_bytes = 0
            size_fmt = db.format_file_size(size_bytes)
            ftype = os.path.splitext(file_name)[1][1:].lower() if "." in file_name else ""
            extracted_at_h = _fmt(datetime.now().isoformat())
            try:
                modified_on_h = _fmt(datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat())
            except Exception:
                modified_on_h = ""

        lines.append(f"File Name: {file_name}")
        lines.append(f"File Size: {size_fmt}")
        lines.append(f"File Type: {ftype}")
        lines.append(f"Extracted At: {extracted_at_h}")
        lines.append(f"Modified On: {modified_on_h}")
        lines.append("")

        if isinstance(metadata, dict):
            for key, value in metadata.items():
                lines.append(f"{key}: {value}")
        else:
            lines.append(str(metadata))

        return "\n".join(lines)

    @staticmethod
    def clear_editor() -> str:
        """Return empty editor placeholder text."""
        return "No metadata loaded.\n\nExtract metadata from a file first, then click 'Editor' to edit it."

    def write_metadata_to_file(self, file_path: str, metadata: dict) -> tuple[bool, str]:
        """Write metadata back to the source file based on file type.
        
        Automatically detects file type and uses appropriate writing method.
        
        Args:
            file_path (str): Path to the file.
            metadata (dict): Metadata dictionary to write.
            
        Returns:
            tuple: (success, message) - Boolean status and informational message.
        """
        if not os.path.exists(file_path):
            return False, "File not found"

        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == '.pdf':
                return self.write_pdf_metadata(file_path, metadata)
            elif ext in ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif']:
                return self.write_image_metadata(file_path, metadata)
            elif ext in ['.mp3', '.wav', '.flac', '.m4a', '.ogg']:
                return self.write_audio_metadata(file_path, metadata)
            elif ext in ['.txt', '.json', '.xml', '.csv', '.md', '.log', '.yaml', '.yml']:
                return self.write_text_metadata(file_path, metadata)
            elif ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
                return self.write_office_metadata(file_path, metadata)
            else:
                return self.write_generic_metadata(file_path, metadata)

        except Exception as e:
            return False, f"Error writing metadata: {str(e)}"

    def write_pdf_metadata(self, file_path: str, metadata: dict) -> tuple[bool, str]:
        """Write metadata to PDF file using PyPDF2.
        
        Maps metadata keys to PDF standard properties. Creates backup before writing.
        
        Args:
            file_path (str): Path to the PDF file.
            metadata (dict): Metadata dictionary to write.
            
        Returns:
            tuple: (success, message) - Boolean status and informational message.
        """
        try:
            from PyPDF2 import PdfReader, PdfWriter

            reader = PdfReader(file_path)
            writer = PdfWriter()

            for page in reader.pages:
                writer.add_page(page)

            pdf_metadata = {}
            key_mapping = {
                'Title': '/Title',
                'Author': '/Author',
                'Subject': '/Subject',
                'Creator': '/Creator',
                'Producer': '/Producer',
                'Keywords': '/Keywords',
            }

            for key, value in metadata.items():
                pdf_key = key_mapping.get(key, f'/{key}')
                pdf_metadata[pdf_key] = str(value)

            writer.add_metadata(pdf_metadata)

            backup_path = file_path + '.backup'
            shutil.copy2(file_path, backup_path)

            try:
                with open(file_path, 'wb') as output_file:
                    writer.write(output_file)

                os.remove(backup_path)
                return True, "PDF metadata written successfully"
            except Exception as e:
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, file_path)
                    os.remove(backup_path)
                raise e

        except ImportError:
            return False, "PyPDF2 not installed. Run: pip install PyPDF2"
        except Exception as e:
            return False, f"PDF write failed: {str(e)}"

    def write_image_metadata(self, file_path: str, metadata: dict) -> tuple[bool, str]:
        """Write metadata to image file using PIL and piexif.
        
        Supports JPEG (EXIF), PNG (PNG text chunks), and other image formats.
        Creates backup before writing.
        
        Args:
            file_path (str): Path to the image file.
            metadata (dict): Metadata dictionary to write.
            
        Returns:
            tuple: (success, message) - Boolean status and informational message.
        """
        try:
            from PIL import Image

            ext = os.path.splitext(file_path)[1].lower()
            img = Image.open(file_path)
            backup_path = file_path + '.backup'

            shutil.copy2(file_path, backup_path)

            try:
                if ext in ['.jpg', '.jpeg', '.tiff', '.tif']:
                    import piexif

                    exif_bytes = img.info.get('exif', None)
                    if exif_bytes:
                        try:
                            exif_dict = piexif.load(exif_bytes)
                        except:
                            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
                    else:
                        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}

                    comment = json.dumps(metadata)
                    exif_dict["Exif"][piexif.ExifIFD.UserComment] = comment.encode('utf-8')

                    try:
                        exif_bytes_new = piexif.dump(exif_dict)

                        if ext in ['.jpg', '.jpeg']:
                            img.save(file_path, quality=95, exif=exif_bytes_new)
                        else:
                            img.save(file_path, exif=exif_bytes_new)

                        os.remove(backup_path)
                        return True, "Image EXIF metadata written successfully"
                    except Exception as e:
                        raise Exception(f"Failed to save EXIF: {str(e)}")

                elif ext == '.png':
                    from PIL import PngImagePlugin

                    meta = PngImagePlugin.PngInfo()
                    for key, value in metadata.items():
                        meta.add_text(str(key), str(value))

                    try:
                        img.save(file_path, pnginfo=meta)
                        os.remove(backup_path)
                        return True, "PNG metadata written successfully"
                    except Exception as e:
                        raise Exception(f"Failed to save PNG: {str(e)}")

                else:
                    os.remove(backup_path)
                    return self.write_generic_metadata(file_path, metadata)

            except ImportError as ie:
                os.remove(backup_path)
                if "piexif" in str(ie):
                    return False, "piexif not installed for JPEG/TIFF. Run: pip install piexif"
                raise ie
            except Exception as e:
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, file_path)
                    os.remove(backup_path)
                raise e

        except ImportError:
            return False, "PIL not installed. Run: pip install Pillow"
        except Exception as e:
            return False, f"Image write failed: {str(e)}"

    def write_audio_metadata(self, file_path: str, metadata: dict) -> tuple[bool, str]:
        """Write metadata to audio file using mutagen.
        
        Supports MP3 (ID3), FLAC, M4A/MP4, and other audio formats.
        Creates backup before writing.
        
        Args:
            file_path (str): Path to the audio file.
            metadata (dict): Metadata dictionary to write.
            
        Returns:
            tuple: (success, message) - Boolean status and informational message.
        """
        try:
            from mutagen.mp3 import MP3
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, COMM
            from mutagen.flac import FLAC
            from mutagen.mp4 import MP4

            ext = os.path.splitext(file_path)[1].lower()
            backup_path = file_path + '.backup'
            shutil.copy2(file_path, backup_path)

            try:
                if ext == '.mp3':
                    audio = MP3(file_path, ID3=ID3)

                    try:
                        audio.add_tags()
                    except:
                        pass

                    if 'Title' in metadata:
                        audio.tags['TIT2'] = TIT2(encoding=3, text=metadata['Title'])
                    if 'Artist' in metadata:
                        audio.tags['TPE1'] = TPE1(encoding=3, text=metadata['Artist'])
                    if 'Album' in metadata:
                        audio.tags['TALB'] = TALB(encoding=3, text=metadata['Album'])

                    comment = json.dumps(metadata)
                    audio.tags['COMM'] = COMM(encoding=3, lang='eng', desc='metadata', text=comment)

                    audio.save()

                elif ext == '.flac':
                    audio = FLAC(file_path)
                    for key, value in metadata.items():
                        audio[key.upper()] = str(value)
                    audio.save()

                elif ext in ['.m4a', '.mp4']:
                    audio = MP4(file_path)
                    audio['\xa9cmt'] = json.dumps(metadata)
                    audio.save()

                else:
                    from mutagen import File
                    audio = File(file_path)
                    if audio is not None:
                        for key, value in metadata.items():
                            audio[key] = str(value)
                        audio.save()

                os.remove(backup_path)
                return True, f"{ext.upper()} metadata written successfully"

            except Exception as e:
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, file_path)
                    os.remove(backup_path)
                raise e

        except ImportError:
            return False, "mutagen not installed. Run: pip install mutagen"
        except Exception as e:
            return False, f"Audio write failed: {str(e)}"

    def write_text_metadata(self, file_path: str, metadata: dict) -> tuple[bool, str]:
        """Write metadata to text-based files by adding/updating metadata header.
        
        Supports JSON, XML, YAML, and plain text files. Adds metadata as comments or JSON.
        Creates backup before writing.
        
        Args:
            file_path (str): Path to the text file.
            metadata (dict): Metadata dictionary to write.
            
        Returns:
            tuple: (success, message) - Boolean status and informational message.
        """
        try:
            ext = os.path.splitext(file_path)[1].lower()

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            backup_path = file_path + '.backup'
            shutil.copy2(file_path, backup_path)

            try:
                if ext == '.json':
                    try:
                        data = json.loads(content)
                        if not isinstance(data, dict):
                            data = {'content': data}
                        data['_metadata'] = metadata
                        new_content = json.dumps(data, indent=2)
                    except:
                        new_content = json.dumps({'_metadata': metadata, 'original': content}, indent=2)

                elif ext in ['.xml']:
                    meta_str = json.dumps(metadata, indent=2)
                    new_content = f"<!-- Metadata:\n{meta_str}\n-->\n{content}"

                elif ext in ['.yaml', '.yml']:
                    meta_lines = ['# Metadata:']
                    for key, value in metadata.items():
                        meta_lines.append(f'#   {key}: {value}')
                    new_content = '\n'.join(meta_lines) + '\n\n' + content

                else:
                    meta_lines = ['# === Metadata ===']
                    for key, value in metadata.items():
                        meta_lines.append(f'# {key}: {value}')
                    meta_lines.append('# ==================\n')
                    new_content = '\n'.join(meta_lines) + '\n' + content

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)

                os.remove(backup_path)
                return True, f"{ext.upper()} metadata written as header/comment"

            except Exception as e:
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, file_path)
                    os.remove(backup_path)
                raise e

        except Exception as e:
            return False, f"Text file write failed: {str(e)}"

    def write_office_metadata(self, file_path: str, metadata: dict) -> tuple[bool, str]:
        """Write metadata to Microsoft Office files.
        
        Supports DOCX files (Word). Sets core properties like Title, Author, Subject.
        Creates backup before writing.
        
        Args:
            file_path (str): Path to the Office file.
            metadata (dict): Metadata dictionary to write.
            
        Returns:
            tuple: (success, message) - Boolean status and informational message.
        """
        try:
            import docx
            from docx.opc.coreprops import CoreProperties

            ext = os.path.splitext(file_path)[1].lower()
            backup_path = file_path + '.backup'
            shutil.copy2(file_path, backup_path)

            try:
                if ext in ['.docx']:
                    doc = docx.Document(file_path)
                    props = doc.core_properties

                    if 'Title' in metadata:
                        props.title = metadata['Title']
                    if 'Author' in metadata:
                        props.author = metadata['Author']
                    if 'Subject' in metadata:
                        props.subject = metadata['Subject']
                    if 'Keywords' in metadata:
                        props.keywords = metadata['Keywords']
                    if 'Comments' in metadata:
                        props.comments = metadata['Comments']

                    doc.save(file_path)
                    os.remove(backup_path)
                    return True, "DOCX metadata written successfully"
                else:
                    return False, f"{ext.upper()} metadata writing requires additional libraries"

            except Exception as e:
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, file_path)
                    os.remove(backup_path)
                raise e

        except ImportError:
            return False, "python-docx not installed. Run: pip install python-docx"
        except Exception as e:
            return False, f"Office file write failed: {str(e)}"

    def write_generic_metadata(self, file_path: str, metadata: dict) -> tuple[bool, str]:
        """Write metadata to any file type by creating a companion .meta.json file.
        
        Fallback method for file types that don't have native metadata support.
        
        Args:
            file_path (str): Path to the file.
            metadata (dict): Metadata dictionary to write.
            
        Returns:
            tuple: (success, message) - Boolean status and informational message.
        """
        try:
            meta_file = file_path + '.meta.json'

            meta_data = {
                'original_file': os.path.basename(file_path),
                'metadata': metadata,
                'updated_at': datetime.now().isoformat()
            }

            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, indent=2)

            return True, f"Metadata saved to companion file: {os.path.basename(meta_file)}"

        except Exception as e:
            return False, f"Companion file write failed: {str(e)}"

    @staticmethod
    def can_write_metadata(file_path: str) -> bool:
        """Check if metadata can be written to this file type.
        
        Args:
            file_path (str): Path to the file.
            
        Returns:
            bool: True if metadata can be written (always returns True currently).
        """
        return True


# Module-level wrapper instance and compatibility functions
_editor = MetadataEditor()


def parse_editor_text(text: str) -> dict:
    """Wrapper: Parse metadata text from editor into structured data."""
    return _editor.parse_editor_text(text)


def validate_metadata(parsed_data: dict) -> tuple[bool, str]:
    """Wrapper: Validate parsed metadata for required fields and format."""
    return _editor.validate_metadata(parsed_data)


def save_edited_metadata(file_path: str, parsed_data: dict) -> tuple[bool, str]:
    """Wrapper: Save edited metadata back to the database."""
    return _editor.save_edited_metadata(file_path, parsed_data)


def get_editable_text(file_path: str, metadata: dict) -> str:
    """Wrapper: Build editable text format from file path and metadata dict."""
    return _editor.get_editable_text(file_path, metadata)


def clear_editor() -> str:
    """Wrapper: Return empty editor placeholder text."""
    return _editor.clear_editor()


def write_metadata_to_file(file_path: str, metadata: dict) -> tuple[bool, str]:
    """Wrapper: Write metadata back to the source file based on file type."""
    return _editor.write_metadata_to_file(file_path, metadata)


def write_pdf_metadata(file_path: str, metadata: dict) -> tuple[bool, str]:
    """Wrapper: Write metadata to a PDF file."""
    return _editor.write_pdf_metadata(file_path, metadata)


def write_image_metadata(file_path: str, metadata: dict) -> tuple[bool, str]:
    """Wrapper: Write metadata to an image file."""
    return _editor.write_image_metadata(file_path, metadata)


def write_audio_metadata(file_path: str, metadata: dict) -> tuple[bool, str]:
    """Wrapper: Write metadata to an audio file."""
    return _editor.write_audio_metadata(file_path, metadata)


def write_text_metadata(file_path: str, metadata: dict) -> tuple[bool, str]:
    """Wrapper: Write metadata to a text-based file."""
    return _editor.write_text_metadata(file_path, metadata)


def write_office_metadata(file_path: str, metadata: dict) -> tuple[bool, str]:
    """Wrapper: Write metadata to a Microsoft Office file."""
    return _editor.write_office_metadata(file_path, metadata)


def write_generic_metadata(file_path: str, metadata: dict) -> tuple[bool, str]:
    """Wrapper: Write metadata to a companion .meta.json file."""
    return _editor.write_generic_metadata(file_path, metadata)


def can_write_metadata(file_path: str) -> bool:
    """Wrapper: Check if metadata can be written to this file type."""
    return _editor.can_write_metadata(file_path)
