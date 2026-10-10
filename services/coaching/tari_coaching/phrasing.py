"""Bilingual (EN/KO) coaching phrasing with rotating variants.

Numbers come only from measurements passed in by the rules. Variants rotate
per rule so repeated feedback does not read like a script.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

TEMPLATES: dict[str, dict[str, dict[str, list[str]]]] = {
    "aim.placement.low": {
        "en": {
            "observation": [
                "Your crosshair entered the angle {med:.1f}° below head level on {k} of the last {n} exposures.",
                "On {k} of {n} recent peeks your crosshair sat {med:.1f}° under the head.",
            ],
            "suggestion": [
                "Raise the placement to head height before the next exposure.",
                "Lift your crosshair to head level while holding; the target should walk into it.",
            ],
            "short": ["Placement {med:.1f}° low. Raise it.", "Crosshair low. Head height."],
            "reasoning": ["Low placement forces a vertical correction after the target appears, adding time before an accurate shot."],
        },
        "ko": {
            "observation": [
                "최근 {n}번의 노출 중 {k}번, 크로스헤어가 머리 높이보다 {med:.1f}° 낮게 위치했습니다.",
                "최근 {n}번의 피크 중 {k}번 조준점이 머리보다 {med:.1f}° 아래에 있었습니다.",
            ],
            "suggestion": [
                "다음 노출 전에 조준점을 머리 높이로 올리세요.",
                "각을 잡을 때 크로스헤어를 머리 높이에 두세요. 적이 조준점으로 걸어 들어오게 하세요.",
            ],
            "short": ["조준 {med:.1f}° 낮음. 올리세요.", "조준점이 낮습니다. 머리 높이로."],
            "reasoning": ["낮은 조준은 적이 나타난 뒤 수직 보정을 강요해 정확한 사격까지 시간이 늘어납니다."],
        },
    },
    "aim.placement.high": {
        "en": {
            "observation": [
                "Your crosshair entered the angle {med:.1f}° above head level on {k} of the last {n} exposures.",
                "On {k} of {n} recent peeks your crosshair sat {med:.1f}° over the head.",
            ],
            "suggestion": ["Lower the placement to head height before the next exposure."],
            "short": ["Placement {med:.1f}° high. Lower it.", "Crosshair high. Head height."],
            "reasoning": ["High placement requires a downward correction before an accurate shot."],
        },
        "ko": {
            "observation": [
                "최근 {n}번의 노출 중 {k}번, 크로스헤어가 머리 높이보다 {med:.1f}° 높게 위치했습니다.",
            ],
            "suggestion": ["다음 노출 전에 조준점을 머리 높이로 내리세요."],
            "short": ["조준 {med:.1f}° 높음. 내리세요."],
            "reasoning": ["높은 조준은 정확한 사격 전에 아래쪽 보정이 필요합니다."],
        },
    },
    "aim.placement.good": {
        "en": {
            "observation": ["Head-level placement is holding: median vertical offset {med:.1f}° over the last {n} exposures."],
            "suggestion": ["Keep the same height as you check the next angle."],
            "short": ["Head level is holding."],
            "reasoning": ["Measured placement is now inside the target band set by your strictness setting."],
        },
        "ko": {
            "observation": ["머리 높이 조준이 유지되고 있습니다: 최근 {n}번 노출의 수직 오차 중앙값 {med:.1f}°."],
            "suggestion": ["다음 각을 확인할 때도 같은 높이를 유지하세요."],
            "short": ["머리 높이 유지 중."],
            "reasoning": ["측정된 조준 높이가 설정한 엄격도 기준 안에 들어왔습니다."],
        },
    },
    "aim.placement.wide": {
        "en": {
            "observation": ["Targets appeared a median of {med:.1f}° {dir} of your crosshair over the last {n} exposures."],
            "suggestion": ["Pre-aim closer to the edge of the angle you're holding."],
            "short": ["Pre-aim closer to the edge."],
            "reasoning": ["Holding off the edge means every peek starts with a horizontal flick."],
        },
        "ko": {
            "observation": ["최근 {n}번의 노출에서 타깃이 크로스헤어 {dir} 중앙값 {med:.1f}° 지점에 나타났습니다."],
            "suggestion": ["지키는 각의 모서리에 더 가깝게 미리 조준하세요."],
            "short": ["모서리에 더 가깝게 조준하세요."],
            "reasoning": ["모서리에서 떨어져 각을 잡으면 매번 수평 플릭으로 시작하게 됩니다."],
        },
    },
    "aim.acquisition.slow": {
        "en": {
            "observation": ["Median time to put the crosshair on the head was {med:.0f} ms over the last {n} targets (target ≤ {thr:.0f} ms)."],
            "suggestion": [
                "Better pre-aim shortens the distance you have to cover. Practice the micro-flick drill to finish movements faster.",
            ],
            "short": ["Acquisition {med:.0f} ms. Tighten pre-aim."],
            "reasoning": ["Acquisition time includes reaction and movement; placement closer to the head reduces the movement part."],
        },
        "ko": {
            "observation": ["최근 {n}개 타깃에서 크로스헤어를 머리에 올리기까지 걸린 시간의 중앙값은 {med:.0f}ms입니다 (기준 {thr:.0f}ms 이하)."],
            "suggestion": ["미리 조준을 잘 해두면 이동 거리가 줄어듭니다. 마이크로 플릭 드릴로 마무리 동작을 연습하세요."],
            "short": ["조준 완료 {med:.0f}ms. 사전 조준을 다듬으세요."],
            "reasoning": ["조준 완료 시간에는 반응과 이동이 포함되며, 머리에 가까운 조준은 이동 시간을 줄입니다."],
        },
    },
    "aim.flick.overshoot": {
        "en": {
            "observation": ["You passed the head on {k} of your last {n} flicks, by a median of {med:.1f}°."],
            "suggestion": ["Decelerate into the end of the flick so the crosshair stops on the head."],
            "short": ["Overshooting. Slow the end of the flick."],
            "reasoning": ["Passing the target forces a correction in the opposite direction before you can fire."],
        },
        "ko": {
            "observation": ["최근 {n}번의 플릭 중 {k}번 머리를 지나쳤습니다 (중앙값 {med:.1f}°)."],
            "suggestion": ["플릭 끝에서 감속해 크로스헤어가 머리 위에서 멈추도록 하세요."],
            "short": ["오버슈팅. 플릭 끝을 늦추세요."],
            "reasoning": ["타깃을 지나치면 사격 전에 반대 방향 보정이 필요합니다."],
        },
    },
    "aim.flick.undershoot": {
        "en": {
            "observation": ["On {k} of your last {n} flicks the first movement stopped short (median {med:.1f}° left) and needed another correction."],
            "suggestion": ["Commit to the full distance on the first movement."],
            "short": ["Stopping short. Commit to the flick."],
            "reasoning": ["Each extra corrective movement adds time before an accurate shot."],
        },
        "ko": {
            "observation": ["최근 {n}번의 플릭 중 {k}번 첫 동작이 목표에 못 미쳐 (중앙값 {med:.1f}° 남음) 추가 보정이 필요했습니다."],
            "suggestion": ["첫 동작에서 끝까지 이동하세요."],
            "short": ["덜 움직입니다. 끝까지 플릭하세요."],
            "reasoning": ["보정 동작이 하나 늘 때마다 정확한 사격까지 시간이 늘어납니다."],
        },
    },
    "aim.shot.unstable": {
        "en": {
            "observation": ["{k} of your last {n} shots were fired while your view was still moving faster than {thr:.0f}°/s."],
            "suggestion": ["Stop, then shoot. Let the crosshair settle before clicking."],
            "short": ["Settle before you shoot."],
            "reasoning": ["Firing during a flick ties accuracy to timing instead of placement."],
        },
        "ko": {
            "observation": ["최근 {n}발 중 {k}발이 시야가 {thr:.0f}°/s 이상으로 움직이는 중에 발사되었습니다."],
            "suggestion": ["멈추고 쏘세요. 크로스헤어가 안정된 뒤 클릭하세요."],
            "short": ["안정된 뒤 쏘세요."],
            "reasoning": ["플릭 도중 사격하면 정확도가 조준이 아닌 타이밍에 좌우됩니다."],
        },
    },
    "aim.shot.moving": {
        "en": {
            "observation": ["{k} of your last {n} shots were fired while moving (your crosshair showed movement error)."],
            "suggestion": ["Counter-strafe to a stop before firing."],
            "short": ["Stop moving before you fire."],
            "reasoning": ["Movement inaccuracy spreads shots regardless of crosshair placement."],
        },
        "ko": {
            "observation": ["최근 {n}발 중 {k}발이 이동 중에 발사되었습니다 (크로스헤어에 이동 오차가 표시됨)."],
            "suggestion": ["카운터 스트레이핑으로 멈춘 뒤 발사하세요."],
            "short": ["멈춘 뒤 쏘세요."],
            "reasoning": ["이동 중 부정확도는 조준 위치와 상관없이 탄을 퍼뜨립니다."],
        },
    },
}

FLASH = {
    "en": {"low": "Low {v:.1f}°", "high": "High {v:.1f}°", "level": "On level", "acquired": "{v:.0f} ms",
           "assumed": "assumed", "right": "to the right", "left": "to the left"},
    "ko": {"low": "낮음 {v:.1f}°", "high": "높음 {v:.1f}°", "level": "높이 적중", "acquired": "{v:.0f}ms",
           "assumed": "추정", "right": "오른쪽", "left": "왼쪽"},
}

SYSTEM = {
    "en": {
        "lab_live": "Training Lab verified. Live coaching is on.",
        "paused": "Live coaching paused: this source is not the verified Training Lab.",
    },
    "ko": {
        "lab_live": "트레이닝 랩이 확인되었습니다. 실시간 코칭을 시작합니다.",
        "paused": "실시간 코칭 일시 중지: 확인된 트레이닝 랩 화면이 아닙니다.",
    },
}


class Phraser:
    def __init__(self, language: str = "en"):
        self.language = language
        self._counts: dict[str, int] = defaultdict(int)

    def render(self, rule_id: str, **values: Any) -> dict[str, str]:
        lang = TEMPLATES[rule_id].get(self.language) or TEMPLATES[rule_id]["en"]
        i = self._counts[rule_id]
        self._counts[rule_id] += 1
        return {part: options[i % len(options)].format(**values) for part, options in lang.items()}

    def flash(self, key: str, **values: Any) -> str:
        return FLASH.get(self.language, FLASH["en"])[key].format(**values)

    def system(self, key: str) -> str:
        return SYSTEM.get(self.language, SYSTEM["en"])[key]
