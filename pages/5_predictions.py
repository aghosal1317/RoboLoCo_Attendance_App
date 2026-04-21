# import streamlit as st
# import pandas as pd
# import plotly.express as px
# from data_loader import load_data
# from model import (
#     train_and_compare,
#     predict_next_meeting,
#     get_feature_importance,
#     FEATURE_LABELS,
# )

# # ----------------------------
# # Page config
# # ----------------------------
# st.title("Attendance Predictions (Beta)")
# st.markdown(
#     "Uses historical attendance patterns to predict who will show up to the next meeting. "
#     "Three models are compared; the best one is used for predictions."
# )

# # ----------------------------
# # Load data
# # ----------------------------
# df = load_data()

# # ----------------------------
# # Train models (cached so it doesn't retrain on every widget interaction)
# # ----------------------------
# @st.cache_data(show_spinner=False)
# def run_training(data_shape, data_hash):
#     return train_and_compare(df)

# data_hash = hash(df.to_json())
# with st.spinner("Training models on historical attendance data..."):
#     results, feature_df = run_training(df.shape, data_hash)

# if results is None:
#     st.error("Not enough attendance data to train a prediction model.")
#     st.stop()

# best_model_name = max(results, key=lambda k: results[k]["cv_mean"])
# best_model = results[best_model_name]["model"]

# # ----------------------------
# # Model Comparison
# # ----------------------------
# st.subheader("Model Comparison")
# st.caption("5-fold cross-validation accuracy across all historical attendance records")

# comp_rows = []
# for name, res in results.items():
#     comp_rows.append({
#         "Model": name,
#         "CV Accuracy": f"{res['cv_mean']}%",
#         "Std Dev": f"±{res['cv_std']}%",
#         "": "⭐ Recommended" if name == best_model_name else "",
#     })

# st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)

# # Why Random Forest wins for this use case
# if best_model_name == "Random Forest":
#     explanation = (
#         "**Why Random Forest?** This dataset has ~70 members and ~60 meetings, which is "
#         "relatively small. Random Forest handles small datasets well without overfitting, "
#         "requires no feature scaling, naturally balances class weight for imbalanced data, "
#         "and provides interpretable feature importances — so you can see exactly what's "
#         "driving each prediction."
#     )
# else:
#     explanation = (
#         f"**{best_model_name}** achieved the highest cross-validation accuracy "
#         f"({results[best_model_name]['cv_mean']}%) on this dataset."
#     )

# st.info(explanation)

# with st.expander("Training data details"):
#     pct_present = round(feature_df["target"].mean() * 100, 1)
#     st.write(f"**Training samples:** {len(feature_df):,}")
#     st.write(f"**Class balance:** {pct_present}% present · {100 - pct_present}% absent in historical data")
#     st.write(
#         "**Features used:** last 3 meeting outcomes, 5-meeting rolling avg, "
#         "10-meeting rolling avg, overall attendance %, consecutive absences streak, "
#         "meeting number in season, subteam"
#     )

# st.divider()

# # ----------------------------
# # Next Meeting Predictions
# # ----------------------------
# st.subheader("Next Meeting Predictions")
# st.caption(f"Using {best_model_name} · Based on each member's most recent attendance patterns")

# with st.spinner("Generating predictions..."):
#     predictions_df = predict_next_meeting(df, best_model)

# will_attend = predictions_df[predictions_df["Prediction"] == "✅ Will Attend"]
# at_risk     = predictions_df[predictions_df["Prediction"] == "❌ At Risk"]

# c1, c2, c3 = st.columns(3)
# c1.metric("Predicted to Attend", len(will_attend))
# c2.metric("Predicted Absent",    len(at_risk))
# predicted_pct = round(len(will_attend) / len(predictions_df) * 100, 1) if len(predictions_df) else 0
# c3.metric("Predicted Attendance %", f"{predicted_pct}%")

# # Subteam filter
# subteams = ["All"] + sorted(
#     [s for s in predictions_df["Subteam"].dropna().unique() if s != ""]
# )
# selected_subteam = st.selectbox("Filter by subteam", subteams)

# display_df = (
#     predictions_df
#     if selected_subteam == "All"
#     else predictions_df[predictions_df["Subteam"] == selected_subteam]
# )

# st.dataframe(
#     display_df,
#     use_container_width=True,
#     hide_index=True,
#     column_config={
#         "Attend Probability": st.column_config.ProgressColumn(
#             "Attend Probability",
#             min_value=0,
#             max_value=100,
#             format="%.1f%%",
#         ),
#         "Current %": st.column_config.NumberColumn(
#             "Current %",
#             format="%.1f%%",
#         ),
#     },
# )

# # Probability distribution
# fig_hist = px.histogram(
#     predictions_df,
#     x="Attend Probability",
#     nbins=20,
#     color="Subteam",
#     title="Distribution of Predicted Attendance Probabilities",
#     labels={"Attend Probability": "Probability of Attending (%)"},
#     barmode="overlay",
# )
# fig_hist.update_traces(opacity=0.75)
# fig_hist.add_vline(
#     x=50, line_dash="dash", line_color="red", annotation_text="50% cutoff"
# )
# st.plotly_chart(fig_hist, use_container_width=True)

# st.divider()

# # ----------------------------
# # At-Risk Members
# # ----------------------------
# st.subheader("At-Risk Members")
# st.caption("Members predicted to miss the next meeting, sorted by lowest probability")

# if at_risk.empty:
#     st.success("No members flagged as at-risk for the next meeting.")
# else:
#     fig_risk = px.bar(
#         at_risk.sort_values("Attend Probability"),
#         x="Attend Probability",
#         y="Name",
#         color="Subteam",
#         orientation="h",
#         title="At-Risk Members — Predicted Attendance Probability",
#         labels={"Attend Probability": "Probability of Attending (%)"},
#     )
#     fig_risk.add_vline(x=50, line_dash="dash", line_color="red")
#     fig_risk.update_layout(yaxis_title="", xaxis_range=[0, 100])
#     st.plotly_chart(fig_risk, use_container_width=True)

# st.divider()

# # ----------------------------
# # Feature Importance
# # ----------------------------
# st.subheader("What Drives the Predictions?")
# st.caption(f"Feature importances from the {best_model_name} model")

# feat_imp = get_feature_importance(best_model)
# if feat_imp is not None:
#     feat_imp["Feature"] = feat_imp["Feature"].map(FEATURE_LABELS)

#     fig_imp = px.bar(
#         feat_imp,
#         x="Importance",
#         y="Feature",
#         orientation="h",
#         title="Feature Importance",
#     )
#     fig_imp.update_layout(yaxis={"categoryorder": "total ascending"})
#     st.plotly_chart(fig_imp, use_container_width=True)

#     st.caption(
#         "Higher importance = the model leans on that signal more. "
#         "Recent meetings (last 1–3) typically outweigh long-term averages because "
#         "attendance behavior tends to cluster in streaks."
#     )
