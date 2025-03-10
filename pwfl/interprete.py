from sflkit.analysis.spectra import Spectrum
from sflkit.evaluation import Scenario

from pwfl.analyze import distances

tex_translation = {
    Spectrum.Tarantula.__name__: "\\TARANTULA{}",
    Spectrum.Ochiai.__name__: "\\OCHIAI{}",
    Spectrum.DStar.__name__: "\\DSTAR{}",
    Spectrum.Naish2.__name__: "\\NAISHTWO{}",
    Spectrum.GP13.__name__: "\\GP{}",
    Scenario.BEST_CASE.value: "Best Case Debugging",
    Scenario.WORST_CASE.value: "Worst Case Debugging",
    Scenario.AVG_CASE.value: "Average Case Debugging",
    "exam": "\\EXAM{}",
    "wasted-effort": "W Effort",
    "line": "w/o \\TW{}",
    "line_line": "\\TW{}$_L$",
    "line_defuse": "\\TW{}$_{DU}$",
    "line_defuses": "\\TW{}$_{DUU}$",
    "line_assert_use": "\\TW{}$_{ADU}$",
    "line_assert_uses": "\\TW{}$_{ADUU}$",
    "PRFL": "\\PRFL{}",
    "PRFL_line": "\\PRFL{}$_L$",
    "PRFL_defuse": "\\PRFL{}$_{DU}$",
    "PRFL_defuses": "\\PRFL{}$_{DUU}$",
    "PRFL_assert_use": "\\PRFL{}$_{ADU}$",
    "PRFL_assert_uses": "\\PRFL{}$_{ADUU}$",
}

scenario_order = [
    Scenario.BEST_CASE.value,
    Scenario.AVG_CASE.value,
    Scenario.WORST_CASE.value,
]

metric_order = [
    Spectrum.Tarantula.__name__,
    Spectrum.Ochiai.__name__,
    Spectrum.DStar.__name__,
    Spectrum.Naish1.__name__,
    Spectrum.Naish2.__name__,
    Spectrum.GP13.__name__,
]

distance_order = [f"line{suffix}" for suffix, _ in distances]
distance_prfl_order = [f"PRFL{suffix}" for suffix, _ in distances]

localization_order = [
    "top-1",
    "top-5",
    "top-10",
    "top-200",
    "exam",
    "wasted-effort",
]

localization_comp = [
    True,
    True,
    True,
    True,
    False,
    False,
]
