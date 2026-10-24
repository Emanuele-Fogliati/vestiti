from datetime import date, timedelta

from app.engine.strategy import DayWeather, StageInput


def stage(index=0, name="Stop", elev=0.0, start=date(2027, 7, 1), days=3, activities=None,
          tmax=22.0, tmin=14.0, rain=0.0, prob=10.0, wind=10.0, source="forecast"):
    ds = [DayWeather(start + timedelta(days=i), tmax, tmin, rain, prob, wind, source) for i in range(days)]
    return StageInput(index=index, stop_id=f"s{index}", name=name, base_elevation_m=elev, start=start,
                      end=start + timedelta(days=days - 1), activities=activities or [{"type": "city"}],
                      days=ds)
