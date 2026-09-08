/** @odoo-module **/

document.addEventListener('DOMContentLoaded', function () {
    const faqItems = document.querySelectorAll('.faq-accordion .faq-item');

    faqItems.forEach((item) => {
        item.addEventListener('toggle', function () {
            if (this.open) {
                faqItems.forEach((other) => {
                    if (other !== this && other.open) {
                        other.removeAttribute('open');
                    }
                });
            }
        });
    });
});