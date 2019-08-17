# This script allows to change the creation date of an image

# Install piexif

# Author: Paco Abato - pacoabato@gmail.com

import piexif

ifile = 'example.jpg'

exif_dict = piexif.load(ifile)
# print(exif_dict) # image's metadata

date = exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal]
print('Previous date: ', date)

creation_date = '2019:08:16 19:00:00'

exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = creation_date
exif_dict['Exif'][piexif.ExifIFD.DateTimeDigitized] = creation_date
exif_bytes = piexif.dump(exif_dict)
piexif.insert(exif_bytes, ifile)

exif_dict = piexif.load(ifile)
date = exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal]
print('Current date: ', date)
