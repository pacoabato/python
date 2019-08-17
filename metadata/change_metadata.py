# This script allows to change the creation_time metadata of a video file

# Install http://ffmpeg.org/ and make accesible its bin directory (like using environment variables)
# Install: pip install ffmpeg-python



''' author: Paco Abato - pacoabato@gmail.com'''

import ffmpeg

ifile = 'example.mp4'
ofile = 'result.mp4'
creationdate = '2013-05-02 22:01:04'
(ffmpeg
 .input(ifile)
 .output(ofile, metadata='creation_time=' + creationdate, codec='copy')
 .run()
 )

# codec='copy' in order to preserve the video quality (also execution time is a lot more faster)

probe = ffmpeg.probe(ifile)
probe2 = ffmpeg.probe(ofile)

print('Previous creation time: ', probe['format']['tags']['creation_time'])
print('Current creation time: ', probe2['format']['tags']['creation_time'])
