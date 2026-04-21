"""
Attendance prediction model for RoboLoCo Attendance Tracker.

Approach: frame each (member, meeting) pair as a classification problem.
Given a member's recent attendance history, predict whether they will
attend the next meeting (1 = present/late, 0 = absent/excused).

Features:
  - prev_1/2/3         : last 3 meeting outcomes (binary)
  - rolling_5/10       : rolling avg over last 5 and 10 meetings
  - overall_pct        : cumulative attendance % at prediction time
  - consecutive_absences: streak of absences going into this meeting
  - meeting_index      : position in the season (captures build-season effects)
  - subteam            : encoded subteam membership

Models compared:
  - Logistic Regression  (interpretable baseline)
  - Random Forest        (recommended — best for this data size)
  - Gradient Boosting    (strong alternative, more sensitive to tuning)
"""

import re
import numpy as np
import pandas as pd
import warnings
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score

warnings.filterwarnings("ignore")

SUBTEAM_MAP = {"Executive": 0, "Loco": 1, "Mechanical": 2, "Software": 3}

FEATURE_NAMES = [
    "prev_1",
    "prev_2",
    "prev_3",
    "rolling_5",
    "rolling_10",
    "overall_pct",
    "consecutive_absences",
    "meeting_index",
    "subteam",
]

FEATURE_LABELS = {
    "prev_1": "Last Meeting",
    "prev_2": "2 Meetings Ago",
    "prev_3": "3 Meetings Ago",
    "rolling_5": "5-Meeting Rolling Avg",
    "rolling_10": "10-Meeting Rolling Avg",
    "overall_pct": "Overall Attendance %",
    "consecutive_absences": "Consecutive Absences",
    "meeting_index": "Meeting # in Season",
    "subteam": "Subteam",
}

_DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{2}")


def _get_date_cols(df):
    """Return only columns that are actual meeting dates (MM/DD/YY format)."""
    return [c for c in df.columns if _DATE_PATTERN.match(str(c))]


def _status_to_binary(s):
    """
    Convert attendance code to binary.
    P / L → 1.0 (attended)
    A / Z → 0.0 (absent)
    O / anything else → NaN (optional — excluded from training)
    """
    s = str(s).strip()
    if s in ("P", "L"):
        return 1.0
    if s in ("A", "Z"):
        return 0.0
    return np.nan


def build_features(df):
    """
    Convert the wide attendance DataFrame into an ML-ready feature matrix.

    Each row in the output represents a single prediction window:
      - target  : did the member attend this meeting?
      - features: based only on past data (no leakage)

    Returns a DataFrame with FEATURE_NAMES columns + 'target'.
    """
    date_cols = _get_date_cols(df)
    rows = []

    for _, member in df.iterrows():
        subteam_enc = SUBTEAM_MAP.get(str(member.get("Subteam", "")), -1)
        statuses = [_status_to_binary(member.get(d, "")) for d in date_cols]

        for i in range(5, len(statuses)):
            target = statuses[i]
            if np.isnan(target):
                continue  # skip optional meetings

            # Build history from all non-optional meetings before this one
            history = [s for s in statuses[:i] if not np.isnan(s)]
            if len(history) < 3:
                continue

            # Lag features
            prev_1 = history[-1]
            prev_2 = history[-2]
            prev_3 = history[-3]

            # Rolling averages
            rolling_5  = float(np.mean(history[-5:]))  if len(history) >= 5  else float(np.mean(history))
            rolling_10 = float(np.mean(history[-10:])) if len(history) >= 10 else float(np.mean(history))
            overall_pct = float(np.mean(history))

            # Consecutive absences streak going into this meeting
            consec_abs = 0
            for s in reversed(history):
                if s == 0.0:
                    consec_abs += 1
                else:
                    break

            rows.append({
                "prev_1": prev_1,
                "prev_2": prev_2,
                "prev_3": prev_3,
                "rolling_5": rolling_5,
                "rolling_10": rolling_10,
                "overall_pct": overall_pct,
                "consecutive_absences": consec_abs,
                "meeting_index": i,
                "subteam": subteam_enc,
                "target": int(target),
            })

    return pd.DataFrame(rows)


def train_and_compare(df):
    """
    Train Logistic Regression, Random Forest, and Gradient Boosting.
    Evaluates each with 5-fold cross-validation.

    Returns:
        results : dict  { model_name → {model, cv_mean, cv_std, cv_scores} }
        feature_df : DataFrame used for training
    """
    feature_df = build_features(df)
    if feature_df.empty or len(feature_df) < 30:
        return None, None

    X = feature_df[FEATURE_NAMES]
    y = feature_df["target"]

    candidates = {
        "Logistic Regression": LogisticRegression(
            max_iter=1000, random_state=42
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=200, random_state=42, class_weight="balanced", n_jobs=-1
        ),
        "Gradient Boosting": GradientBoostingClassifier(
            n_estimators=100, learning_rate=0.1, max_depth=4, random_state=42
        ),
    }

    results = {}
    for name, model in candidates.items():
        cv_scores = cross_val_score(model, X, y, cv=5, scoring="accuracy")
        model.fit(X, y)
        results[name] = {
            "model": model,
            "cv_mean": round(float(cv_scores.mean()) * 100, 1),
            "cv_std":  round(float(cv_scores.std())  * 100, 1),
            "cv_scores": cv_scores,
        }

    return results, feature_df


def predict_next_meeting(df, model):
    """
    For each member, predict their probability of attending the next meeting.

    Returns a DataFrame sorted by predicted probability (descending).
    """
    date_cols = _get_date_cols(df)
    n_meetings = len(date_cols)
    predictions = []

    for _, member in df.iterrows():
        statuses = [_status_to_binary(member.get(d, "")) for d in date_cols]
        history = [s for s in statuses if not np.isnan(s)]

        if len(history) < 3:
            continue

        subteam_enc = SUBTEAM_MAP.get(str(member.get("Subteam", "")), -1)

        consec_abs = 0
        for s in reversed(history):
            if s == 0.0:
                consec_abs += 1
            else:
                break

        features = pd.DataFrame([{
            "prev_1": history[-1],
            "prev_2": history[-2],
            "prev_3": history[-3],
            "rolling_5":  float(np.mean(history[-5:]))  if len(history) >= 5  else float(np.mean(history)),
            "rolling_10": float(np.mean(history[-10:])) if len(history) >= 10 else float(np.mean(history)),
            "overall_pct": float(np.mean(history)),
            "consecutive_absences": consec_abs,
            "meeting_index": n_meetings,  # next meeting
            "subteam": subteam_enc,
        }])

        prob = float(model.predict_proba(features)[0][1])

        first = str(member.get("First Name", "")).strip()
        last  = str(member.get("Last Name",  "")).strip()
        full  = str(member.get("Full Name",  f"{first} {last}")).strip()

        current_pct = member.get("% Meetings Attended", 0)
        try:
            current_pct = round(float(current_pct), 1)
        except (TypeError, ValueError):
            current_pct = 0.0

        predictions.append({
            "Name": full or f"{first} {last}",
            "Subteam": member.get("Subteam", ""),
            "Current %": current_pct,
            "Attend Probability": round(prob * 100, 1),
            "Prediction": "✅ Will Attend" if prob >= 0.5 else "❌ At Risk",
        })

    return (
        pd.DataFrame(predictions)
        .sort_values("Attend Probability", ascending=False)
        .reset_index(drop=True)
    )


def get_feature_importance(model):
    """
    Return a DataFrame of feature importances.
    Works for Random Forest and Gradient Boosting (feature_importances_)
    and Logistic Regression (|coef_|).
    """
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    elif hasattr(model, "coef_"):
        importances = np.abs(model.coef_[0])
    else:
        return None

    return (
        pd.DataFrame({"Feature": FEATURE_NAMES, "Importance": importances})
        .sort_values("Importance", ascending=False)
        .reset_index(drop=True)
    )
