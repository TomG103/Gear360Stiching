import os
import piexif
import logging

class MetadataHandler:
    def __init__(self):
        # 360 Photo XMP Metadata template
        self.xmp_template = b"""<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 5.1.0-jc003">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
        xmlns:GPano="http://ns.google.com/photos/1.0/panorama/"
        GPano:UsePanoramaViewer="True"
        GPano:ProjectionType="equirectangular"
        GPano:CroppedAreaImageWidthPixels="{width}"
        GPano:CroppedAreaImageHeightPixels="{height}"
        GPano:FullPanoWidthPixels="{width}"
        GPano:FullPanoHeightPixels="{height}"
        GPano:CroppedAreaLeftPixels="0"
        GPano:CroppedAreaTopPixels="0">
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""

    def copy_exif(self, src_path, dst_path):
        """Copies EXIF data from src to dst, preserving original metadata."""
        try:
            exif_dict = piexif.load(src_path)
            exif_bytes = piexif.dump(exif_dict)
            piexif.insert(exif_bytes, dst_path)
            logging.info(f"Copied EXIF metadata from {src_path} to {dst_path}")
            return True
        except Exception as e:
            logging.warning(f"Failed to copy EXIF data: {e}")
            return False

    def inject_360_xmp(self, file_path, width, height):
        """Injects 360 XMP metadata into the JPEG file."""
        try:
            xmp_data = self.xmp_template.replace(b"{width}", str(width).encode('utf-8'))
            xmp_data = xmp_data.replace(b"{height}", str(height).encode('utf-8'))

            with open(file_path, 'rb') as f:
                img_data = f.read()

            # Find where EXIF ends and insert XMP
            # XMP is stored in APP1 segment (0xFFE1) just like EXIF

            # Simple approach: piexif doesn't natively handle XMP insertion easily without corrupting
            # However, we can construct an APP1 segment for XMP
            xmp_segment = b'\xff\xe1' + (len(xmp_data) + 31).to_bytes(2, 'big') + b'http://ns.adobe.com/xap/1.0/\x00' + xmp_data

            # Find SOS (Start of Scan) marker 0xFFDA to insert before it, or after APP0/APP1
            idx = img_data.find(b'\xff\xe1')
            if idx == -1:
                idx = img_data.find(b'\xff\xdb') # DQT

            if idx != -1:
                new_img_data = img_data[:idx] + xmp_segment + img_data[idx:]
                with open(file_path, 'wb') as f:
                    f.write(new_img_data)
                logging.info(f"Injected 360 XMP metadata into {file_path}")
                return True
            else:
                logging.warning(f"Could not find valid JPEG marker to inject XMP in {file_path}")
                return False

        except Exception as e:
            logging.warning(f"Failed to inject XMP data: {e}")
            return False

    def process_metadata(self, src_path, dst_path, width, height):
        self.copy_exif(src_path, dst_path)
        self.inject_360_xmp(dst_path, width, height)

if __name__ == "__main__":
    # Test MetadataHandler
    handler = MetadataHandler()
    print("MetadataHandler initialized successfully.")
