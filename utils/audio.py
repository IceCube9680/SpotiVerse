
import os
import subprocess
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
from mutagen import File
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TYER, TCON, APIC, ID3NoHeaderError
import logging
import platform
import stat

logger = logging.getLogger(__name__)

class AudioProcessor:
    def __init__(self):
        self.ffmpeg_path = self.get_ffmpeg_path()
    
    def get_ffmpeg_path(self):
        """Get FFmpeg path, download if not available"""
        # Check if ffmpeg is in PATH
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return "ffmpeg"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        # Check if ffmpeg is in project directory
        ffmpeg_dir = os.path.join(os.getcwd(), "ffmpeg")
        if platform.system() == "Windows":
            ffmpeg_exe = os.path.join(ffmpeg_dir, "bin", "ffmpeg.exe")
        else:
            ffmpeg_exe = os.path.join(ffmpeg_dir, "bin", "ffmpeg")
        
        if os.path.exists(ffmpeg_exe):
            # Set executable permissions on Windows
            if platform.system() == "Windows":
                try:
                    os.chmod(ffmpeg_exe, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
                except Exception as e:
                    logger.warning(f"Could not set permissions on ffmpeg: {e}")
            return ffmpeg_exe
        
        # FFmpeg not found, download it
        logger.warning("FFmpeg not found. Downloading...")
        return self.download_ffmpeg()
    
    def download_ffmpeg(self):
        """Download and extract FFmpeg"""
        ffmpeg_dir = os.path.join(os.getcwd(), "ffmpeg")
        os.makedirs(ffmpeg_dir, exist_ok=True)
        
        if platform.system() == "Windows":
            # Download Windows build
            ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
            zip_path = os.path.join(ffmpeg_dir, "ffmpeg.zip")
            
            try:
                # Download
                logger.info("Downloading FFmpeg...")
                import urllib.request
                urllib.request.urlretrieve(ffmpeg_url, zip_path)
                
                # Extract
                import zipfile
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(ffmpeg_dir)
                
                # Find the extracted folder
                for item in os.listdir(ffmpeg_dir):
                    if item.startswith("ffmpeg") and os.path.isdir(os.path.join(ffmpeg_dir, item)):
                        extracted_dir = os.path.join(ffmpeg_dir, item)
                        # Move contents to ffmpeg directory
                        for file in os.listdir(extracted_dir):
                            os.rename(
                                os.path.join(extracted_dir, file),
                                os.path.join(ffmpeg_dir, file)
                            )
                        os.rmdir(extracted_dir)
                        break
                
                # Clean up
                os.remove(zip_path)
                
                ffmpeg_exe = os.path.join(ffmpeg_dir, "bin", "ffmpeg.exe")
                if os.path.exists(ffmpeg_exe):
                    # Set executable permissions
                    try:
                        os.chmod(ffmpeg_exe, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
                    except Exception as e:
                        logger.warning(f"Could not set permissions on ffmpeg: {e}")
                    
                    logger.info("FFmpeg downloaded successfully")
                    return ffmpeg_exe
                
            except Exception as e:
                logger.error(f"Failed to download FFmpeg: {e}")
        
        # Fallback: try to use system ffmpeg or return error
        logger.error("FFmpeg is required for audio processing. Please install it manually.")
        return "ffmpeg"  # This will fail but we'll handle the error
    
    def convert_audio(self, input_path, output_path, format_type, quality):
        """
        Convert audio to desired format and quality using ffmpeg
        """
        try:
            # Make sure input file exists and is readable
            if not os.path.exists(input_path):
                logger.error(f"Input file does not exist: {input_path}")
                return False
            
            # Make sure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            if format_type == "mp3":
                bitrate = f"{quality}k"
                cmd = [
                    self.ffmpeg_path, "-i", input_path,
                    "-codec:a", "libmp3lame",
                    "-b:a", bitrate,
                    "-vn", output_path,
                    "-y"
                ]
            elif format_type == "flac":
                if quality == "low":
                    compression = "0"
                elif quality == "medium":
                    compression = "5"
                else:  # high
                    compression = "8"
                
                cmd = [
                    self.ffmpeg_path, "-i", input_path,
                    "-codec:a", "flac",
                    "-compression_level", compression,
                    "-vn", output_path,
                    "-y"
                ]
            else:
                raise ValueError(f"Unsupported format: {format_type}")
            
            # Run conversion with better error handling
            logger.info(f"Running FFmpeg command: {' '.join(cmd)}")
            
            # Use shell=True on Windows to avoid permission issues
            use_shell = platform.system() == "Windows"
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=300,  # 5 minute timeout
                shell=use_shell
            )
            
            if result.returncode != 0:
                logger.error(f"FFmpeg conversion failed: {result.stderr}")
                # Check if output file was created despite error
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except Exception:
                        pass
                return False
            
            # Verify output file was created
            if not os.path.exists(output_path):
                logger.error(f"Output file was not created: {output_path}")
                return False
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg conversion timed out after 5 minutes")
            return False
        except PermissionError as e:
            logger.error(f"Permission error in audio conversion: {e}")
            # Try alternative approach
            return self.convert_audio_alternative(input_path, output_path, format_type, quality)
        except Exception as e:
            logger.error(f"Unexpected error in audio conversion: {e}")
            return False
    
    def convert_audio_alternative(self, input_path, output_path, format_type, quality):
        """
        Alternative audio conversion method for when FFmpeg has permission issues
        """
        try:
            # Try using python-based audio conversion as fallback
            if format_type == "mp3":
                # Use pydub if available
                try:
                    from pydub import AudioSegment
                    
                    audio = AudioSegment.from_file(input_path)
                    
                    if quality == 64:
                        bitrate = "64k"
                    elif quality == 128:
                        bitrate = "128k"
                    elif quality == 192:
                        bitrate = "192k"
                    elif quality == 256:
                        bitrate = "256k"
                    else:  # 320 or default
                        bitrate = "320k"
                    
                    audio.export(output_path, format="mp3", bitrate=bitrate)
                    return True
                    
                except ImportError:
                    logger.error("pydub not available for fallback conversion")
                    return False
                    
            else:
                # For other formats, we'll need to rely on FFmpeg
                logger.error("No alternative conversion method available for this format")
                return False
                
        except Exception as e:
            logger.error(f"Alternative conversion failed: {e}")
            return False
    
    @staticmethod
    def add_metadata(audio_path, metadata, thumbnail_url=None):
        """Add metadata to audio file"""
        try:
            meta = metadata or {}
            title = meta.get("title") or "Unknown Title"
            artist = meta.get("artist") or "Unknown Artist"
            album = meta.get("album") or "Unknown Album"
            year = str(meta.get("year") or "2023")
            genre = meta.get("genre") or "Music"

            if audio_path.endswith('.mp3'):
                try:
                    audio = ID3(audio_path)
                except ID3NoHeaderError:
                    audio = ID3()
                    audio.save(audio_path)
                    audio = ID3(audio_path)
                
                # Add text metadata
                audio["TIT2"] = TIT2(encoding=3, text=title)
                audio["TPE1"] = TPE1(encoding=3, text=artist)
                audio["TALB"] = TALB(encoding=3, text=album)
                audio["TYER"] = TYER(encoding=3, text=year)
                audio["TCON"] = TCON(encoding=3, text=genre)
                
                # Add thumbnail if available
                if thumbnail_url:
                    try:
                        response = requests.get(thumbnail_url, timeout=10)
                        if response.status_code == 200:
                            img_data = response.content
                            audio["APIC"] = APIC(
                                encoding=3,
                                mime='image/jpeg',
                                type=3,  # 3 is for cover image
                                desc='Cover',
                                data=img_data
                            )
                    except Exception as e:
                        logger.error(f"Failed to add thumbnail: {e}")
                
                audio.save()
                
            elif audio_path.endswith('.flac'):
                audio = FLAC(audio_path)
                
                # Add text metadata
                audio["title"] = title
                audio["artist"] = artist
                audio["album"] = album
                audio["date"] = year
                audio["genre"] = genre
                
                # Add thumbnail if available
                if thumbnail_url:
                    try:
                        response = requests.get(thumbnail_url, timeout=10)
                        if response.status_code == 200:
                            img_data = response.content
                            image = Picture()
                            image.type = 3  # 3 is for cover image
                            image.mime = 'image/jpeg'
                            image.desc = 'Cover'
                            image.data = img_data
                            audio.add_picture(image)
                    except Exception as e:
                        logger.error(f"Failed to add thumbnail: {e}")
                
                audio.save()
            
            return True
            
        except Exception as e:
            logger.error(f"Metadata addition failed: {e}")
            return False
    
    @staticmethod
    def generate_thumbnail(title, artist, size=(500, 500)):
        """Generate a simple thumbnail with title and artist"""
        try:
            safe_t = str(title or "Unknown Title")
            safe_a = str(artist or "Unknown Artist")

            # Create a blank image with a gradient background
            img = Image.new('RGB', size, color=(41, 128, 185))
            draw = ImageDraw.Draw(img)
            
            # Try to load a font, fall back to default if not available
            try:
                title_font = ImageFont.truetype("arialbd.ttf", 40)
                artist_font = ImageFont.truetype("arial.ttf", 30)
            except Exception:
                title_font = ImageFont.load_default()
                artist_font = ImageFont.load_default()
            
            # Calculate text positions
            title_bbox = draw.textbbox((0, 0), safe_t, font=title_font)
            artist_bbox = draw.textbbox((0, 0), safe_a, font=artist_font)
            
            title_width = title_bbox[2] - title_bbox[0]
            title_height = title_bbox[3] - title_bbox[1]
            
            artist_width = artist_bbox[2] - artist_bbox[0]
            artist_height = artist_bbox[3] - artist_bbox[1]
            
            title_x = (size[0] - title_width) // 2
            title_y = (size[1] - title_height - artist_height - 20) // 2
            
            artist_x = (size[0] - artist_width) // 2
            artist_y = title_y + title_height + 20
            
            # Draw text
            draw.text((title_x, title_y), safe_t, font=title_font, fill=(255, 255, 255))
            draw.text((artist_x, artist_y), safe_a, font=artist_font, fill=(236, 240, 241))
            
            # Save thumbnail (sanitize title and artist for safe filename)
            import re
            file_t = re.sub(r'[^\w\s-]', '', safe_t).strip() or "title"
            file_a = re.sub(r'[^\w\s-]', '', safe_a).strip() or "artist"
            thumbnail_path = f"data/thumbnails/{file_t}_{file_a}.jpg"
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
            img.save(thumbnail_path)
            
            return thumbnail_path
            
        except Exception as e:
            logger.error(f"Thumbnail generation failed: {e}")
            return None
