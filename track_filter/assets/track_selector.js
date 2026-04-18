/**
 * Track Selector — visual enhancement for the team creation form.
 *
 * Highlights the selected track option with red/blue styling
 * and validates that a track is chosen before form submission.
 */
document.addEventListener("DOMContentLoaded", function () {
    var select = document.getElementById("track");
    if (!select) return;

    select.addEventListener("change", function () {
        var form = select.closest("form");
        if (!form) return;

        // Reset
        form.classList.remove("track-selected-red", "track-selected-blue");

        if (select.value === "red-team") {
            form.classList.add("track-selected-red");
        } else if (select.value === "blue-team") {
            form.classList.add("track-selected-blue");
        }
    });
});
