/** @odoo-module **/

document.addEventListener("click", function (ev) {
    const summary = ev.target.closest(".faq-accordion .faq-item summary");
    if (!summary) return;

    const currentItem = summary.closest(".faq-item");
    if (!currentItem) return;

    const accordion = currentItem.closest(".faq-accordion");
    if (!accordion) return;

    // Close all other open accordion items in the target accordion
    const items = accordion.querySelectorAll(".faq-item");
    items.forEach((item) => {
        if (item !== currentItem && item.hasAttribute("open")) {
            item.removeAttribute("open");
        }
    });
});