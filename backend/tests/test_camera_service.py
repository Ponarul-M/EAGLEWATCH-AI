from services.camera_service import WebcamSource, VideoFileSource, create_camera_source


def test_numeric_source_creates_webcam():
    cam = create_camera_source("0")
    assert isinstance(cam, WebcamSource)
    assert cam.loops is False


def test_path_source_creates_video_file():
    cam = create_camera_source("sample_videos/demo.mp4")
    assert isinstance(cam, VideoFileSource)
    assert cam.loops is True


def test_video_file_source_missing_file_raises():
    cam = VideoFileSource("/definitely/does/not/exist.mp4")
    try:
        cam.open()
        assert False, "expected RuntimeError for missing file"
    except RuntimeError as exc:
        assert "not found" in str(exc)
