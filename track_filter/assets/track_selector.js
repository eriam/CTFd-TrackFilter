/**
 * Track Selector — visual enhancement for the team creation form.
 *
 * Highlights the form with the accent colour of the selected track. The
 * colour comes from the option's data-accent attribute, rendered from the
 * plugin configuration.
 */
document.addEventListener("DOMContentLoaded", function () {
    var select = document.getElementById("track");
    if (!select) return;

    select.addEventListener("change", function () {
        var form = select.closest("form");
        if (!form) return;

        var option = select.options[select.selectedIndex];
        var accent = option ? option.getAttribute("data-accent") : "";

        if (accent) {
            form.style.setProperty("--track-selected-accent", accent);
            form.style.setProperty("--track-selected-glow", accent + "4d");
            form.classList.add("track-selected");
        } else {
            form.classList.remove("track-selected");
        }
    });
});
