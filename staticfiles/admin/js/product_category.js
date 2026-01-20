(function($) {
    $(document).ready(function() {
        var $categorySelect = $('#id_category');
        var $customCategoryRow = $('#id_custom_category').closest('.field-custom_category');

        function toggleCustomCategory() {
            if ($categorySelect.val() === 'OTHER') {
                $customCategoryRow.show();
                // Change the field from hidden to visible input
                $('#id_custom_category').attr('type', 'text').show();
            } else {
                $customCategoryRow.hide();
                // Clear the custom category value when not OTHER
                $('#id_custom_category').val('');
            }
        }

        // Initial check
        toggleCustomCategory();

        // Listen for changes
        $categorySelect.on('change', toggleCustomCategory);
    });
})(django.jQuery);