from shortform_cli import build_parser


def test_shortform_cli_analyze_defaults():
    args = build_parser().parse_args(["analyze", "source.mp4"])
    assert args.command == "analyze"
    assert args.count == 3
    assert args.duration == 30.0


def test_shortform_cli_render_accepts_vertical_options():
    args = build_parser().parse_args([
        "render", "source.mp4",
        "--count", "4",
        "--duration", "22",
        "--width", "720",
        "--height", "1280",
    ])
    assert args.command == "render"
    assert args.count == 4
    assert args.duration == 22
    assert (args.width, args.height) == (720, 1280)


def test_shortform_cli_quality_defaults():
    args = build_parser().parse_args(["render-quality", "source.mp4"])
    assert args.command == "render-quality"
    assert args.quality == "high"
    assert args.whisper_model == "medium"
    assert args.no_whisper is False


if __name__ == "__main__":
    test_shortform_cli_analyze_defaults()
    test_shortform_cli_render_accepts_vertical_options()
    test_shortform_cli_quality_defaults()
    print("ok")
