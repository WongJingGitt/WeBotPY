from base64 import b64decode

import lz4.block

def parse_compressed_content(compressed_content: str):
    bytes_content = b64decode(compressed_content)
    prase_result = lz4.block.decompress(bytes_content, uncompressed_size=len(bytes_content) << 10)
    return prase_result.decode().replace("\x00", "")