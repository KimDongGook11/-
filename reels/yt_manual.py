"""보관된 장편을 유튜브에 직접 올리기 (새 썸네일 디자인으로 다시 만들어서).
사용: python -m reels.yt_manual jobs/xxx.json"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from . import doubleexp, graphics, realphoto, storage, telegram, youtube


def main(job_path):
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    d = Path(tempfile.mkdtemp())
    video = storage.download(job["tag"], str(d / "long.mp4"), name=job.get("video_name"))
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                               capture_output=True, text=True).stdout.strip())
    frame = d / "frame.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{dur / 3:.1f}", "-i", video, "-frames:v", "1", str(frame)],
                   check=True)
    real, credit = realphoto.company_photo(job.get("wiki_titles") or [job.get("company", "")], d,
                                           episode=f"{job.get('thumb_sub', '')} — {job['thumb_line1']} {job['thumb_line2']}")
    if real:
        print("썸네일 실제 사진:", credit)
        thumb = graphics.thumbnail_photo(real, job["thumb_line1"], job["thumb_line2"], job.get("thumb_sub", ""),
                                         job.get("ep"), d / "thumbnail_new.jpg")
    else:
        fig = doubleexp.figure_for(job.get("country_ko"), d, seed=job.get("ep"))
        print("인물 합성:", "성공" if fig else "실패(인물 없이)")
        thumb = graphics.thumbnail(str(frame), job["thumb_line1"], job["thumb_line2"], job.get("thumb_sub", ""),
                                   job.get("ep"), d / "thumbnail_new.jpg", figure=fig)
    storage.add_asset(job["tag"], str(thumb), "thumbnail_new.jpg")
    print("유튜브 업로드 시작:", youtube.channel())
    desc = job["description"] + (f"\n🖼 썸네일 사진: {credit}" if real else "")
    vid, st = youtube.upload(video, job["title"], desc, job.get("tags", []),
                             privacy=job.get("privacy", "public"), thumb=str(thumb))
    print(f"완료: https://youtu.be/{vid} ({st})")
    if telegram.enabled():
        telegram.send_photo(str(thumb), "🖼 새 썸네일")
        telegram.send_message(f"🎉 유튜브 게시 완료! (상태: {st})\nhttps://youtu.be/{vid}")


if __name__ == "__main__":
    main(sys.argv[1])
