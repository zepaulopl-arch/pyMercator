
# AURUM Etapa 8 trust report dispatcher
import sys as _aurum_trust_sys
if len(_aurum_trust_sys.argv) > 2 and _aurum_trust_sys.argv[1] == "trust":
    from pymercator.trust.cli import main as _aurum_trust_main
    _aurum_trust_main(_aurum_trust_sys.argv[2:])
    raise SystemExit(0)


# AURUM Etapa 7 thin CLI dispatchers
import sys as _aurum_stage7_sys

if len(_aurum_stage7_sys.argv) > 2 and _aurum_stage7_sys.argv[1] == "signal" and _aurum_stage7_sys.argv[2] == "run":
    from pymercator.cli_signal_run import main as _aurum_signal_run_main
    _aurum_signal_run_main(_aurum_stage7_sys.argv[3:])
    raise SystemExit(0)

if len(_aurum_stage7_sys.argv) > 2 and _aurum_stage7_sys.argv[1] == "review" and _aurum_stage7_sys.argv[2] == "run":
    from pymercator.cli_review_run import main as _aurum_review_run_main
    _aurum_review_run_main(_aurum_stage7_sys.argv[3:])
    raise SystemExit(0)

if len(_aurum_stage7_sys.argv) > 2 and _aurum_stage7_sys.argv[1] == "train" and _aurum_stage7_sys.argv[2] == "run":
    from pymercator.cli_train_run import main as _aurum_train_run_main
    _aurum_train_run_main(_aurum_stage7_sys.argv[3:])
    raise SystemExit(0)

if len(_aurum_stage7_sys.argv) > 2 and _aurum_stage7_sys.argv[1] == "weekend" and _aurum_stage7_sys.argv[2] == "run":
    from pymercator.cli_weekend_run import main as _aurum_weekend_run_main
    _aurum_weekend_run_main(_aurum_stage7_sys.argv[3:])
    raise SystemExit(0)


# AURUM Training Audit CLI
import sys as _aurum_training_sys
if (
    len(_aurum_training_sys.argv) > 2
    and _aurum_training_sys.argv[1] == "train"
    and _aurum_training_sys.argv[2] in {"audit", "compare", "history"}
):
    from pymercator.training.cli import main as _aurum_training_main
    _aurum_training_main(_aurum_training_sys.argv[2:])
    raise SystemExit(0)


# AURUM Engine Registry CLI
import sys as _aurum_engines_sys
if len(_aurum_engines_sys.argv) > 1 and _aurum_engines_sys.argv[1] == "engines":
    from pymercator.engines.cli import main as _aurum_engines_main
    _aurum_engines_main(_aurum_engines_sys.argv[2:])
    raise SystemExit(0)

# AURUM_FEATURES_INTERCEPT
import sys as _aurum_features_sys
if len(_aurum_features_sys.argv) > 1 and _aurum_features_sys.argv[1] == "features":
    from pymercator.features.cli import main as _aurum_features_main
    raise SystemExit(_aurum_features_main(_aurum_features_sys.argv[2:]))
from pymercator.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
