from __future__ import annotations

from oilsignal.api.app import _load_latest
from oilsignal.config import settings
from oilsignal.reports.renderers import render_markdown
from oilsignal.reports.weekly import WeeklyPetroleumBrief


def main() -> None:
    observations = _load_latest(settings.data_dir)
    report = WeeklyPetroleumBrief().build(observations)
    print(render_markdown(report))


if __name__ == "__main__":
    main()
