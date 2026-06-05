from pathlib import Path
import subprocess

import click


@click.command()
@click.option("-f", "--framerate", type=int, default=24)
@click.option("-q", "--quality", type=int, default=20)
@click.option("-g", "--glob", default="*.png", show_default=True)
@click.option("-p", "--palindromic", is_flag=True)
@click.argument(
    "output_file",
    type=click.Path(file_okay=True, dir_okay=False, writable=True, path_type=Path),
)
def create_movie(
    framerate: int, quality: int, glob: str, palindromic: bool, output_file: Path
):
    """Create a movie from a series of image files."""
    output_file_tmp = output_file.with_stem(f"{output_file.stem}_tmp")
    output_file_rev = output_file.with_stem(f"{output_file.stem}_rev")
    videofiles_tmp = output_file.with_suffix(".txt")

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
        output_file_tmp.unlink()
        output_file_rev.unlink()
        videofiles_tmp.unlink()
