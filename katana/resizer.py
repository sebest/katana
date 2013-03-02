import logging
import PIL
from PIL import Image, ImageOps
from math import ceil, fabs

logger = logging.getLogger('resizer')

def resize(src, dst, width=0, height=0, fit=True, quality=75):

    try:
        img = Image.open(src)
    except IOError as e:
        logger.error('resize %s: (%dx%d) corrupt image [%s]', src, width, height, e)
        return False

    origin_width, origin_height = img.size
    if origin_height == origin_width == 0:
        return False

    if not width:
        width  = int(ceil(origin_width / (float(origin_height) / height)))
    if not height:
        height = int(ceil(origin_height / (float(origin_width) / width)))

    logger.debug('resize %s: (%dx%d) => (%dx%d) mode=%s quality=%d', src, origin_width, origin_height, width, height, 'fit' if fit else 'fill', quality)

    if fit:
        img = ImageOps.fit(img, (width, height), Image.ANTIALIAS)
    else:
        img = img.copy()
        img.thumbnail((width, height), Image.ANTIALIAS)
    img.save(dst, quality=quality)
    return True
