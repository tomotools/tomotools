import subprocess
from os import path, remove

import click


@click.command()
@click.option("-f", "--framerate", type=int, default=24)
@click.option("-q", "--quality", type=int, default=20)
@click.option("-g", "--glob", default="*.png", show_default=True)
@click.option("-p", "--palindromic", is_flag=True)
@click.argument("output_file")
def create_movie(framerate, quality, glob, palindromic, output_file):
    """Create a movie from a series of image files"""
    dir = path.dirname(output_file)
    basename, ext = path.splitext(path.basename(output_file))
    output_file_tmp = path.join(dir, f"{basename}_tmp{ext}")
    output_file_rev = path.join(dir, f"{basename}_rev{ext}")
    videofiles_tmp = path.join(dir, f"{basename}.txt")

    cmd = [
        "ffmpeg",
        "-framerate",
        str(framerate),
        "-f",
        "image2",
        "-pattern_type",
        "glob",
        "-i",
        glob,
        "-vf",
        "pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2",
        "-vcodec",
        "libx264",
        "-crf",
        str(quality),
        "-pix_fmt",
        "yuv420p",
        output_file_tmp if palindromic else output_file,
    ]
    subprocess.run(cmd)
    if palindromic:
        with open(videofiles_tmp, "w") as f:
            f.write(f"file {output_file_tmp}\nfile {output_file_rev}\n")
        subprocess.run(
            ["ffmpeg", "-i", output_file_tmp, "-vf", "reverse", "-y", output_file_rev]
        )
        subprocess.run(
            [
                "ffmpeg",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                videofiles_tmp,
                "-c",
                "copy",
                output_file,
            ]
        )
        remove(output_file_tmp)
        remove(output_file_rev)
        remove(videofiles_tmp)
