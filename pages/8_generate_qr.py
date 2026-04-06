import streamlit as st
import qrcode
import io
from data_loader import load_data

st.title("Member QR Codes")
st.caption("Each member gets a unique QR code. They can save it to their phone or print it to scan at meetings.")

df = load_data()
df["Full Name"] = df["First Name"].str.strip() + " " + df["Last Name"].str.strip()

# Filter out subteam header rows
members = df[df["Full Name"].str.strip() != ""].copy()

# Search + subteam filter
search_col, subteam_col = st.columns([2, 1])

with search_col:
    search = st.text_input("Search member", placeholder="Type a name...")

with subteam_col:
    subteams = sorted(members["Subteam"].dropna().unique().tolist())
    selected_subteam = st.selectbox("Filter by subteam", ["All"] + subteams)

if search:
    members = members[members["Full Name"].str.contains(search, case=False, na=False)]
if selected_subteam != "All":
    members = members[members["Subteam"] == selected_subteam]

st.markdown(f"Showing **{len(members)}** members")
st.divider()

def make_qr_bytes(full_name: str) -> bytes:
    data = f"ROBOLOCO:{full_name}"
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# Display in a 4-column grid
cols_per_row = 4
names = members["Full Name"].tolist()

for row_start in range(0, len(names), cols_per_row):
    row_names = names[row_start : row_start + cols_per_row]
    cols = st.columns(cols_per_row)
    for col, name in zip(cols, row_names):
        qr_bytes = make_qr_bytes(name)
        with col:
            st.image(qr_bytes, caption=name, use_container_width=True)
            st.download_button(
                label="Download",
                data=qr_bytes,
                file_name=f"{name.replace(' ', '_')}_qr.png",
                mime="image/png",
                key=f"dl_{name}"
            )
