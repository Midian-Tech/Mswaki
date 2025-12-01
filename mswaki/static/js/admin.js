document.addEventListener('DOMContentLoaded', function() {
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const sidebar = document.querySelector('.admin-sidebar');
    let overlay = document.querySelector('.mobile-menu-overlay');
    const html = document.documentElement;
    let isAnimating = false;
    const ANIMATION_DURATION = 300; // ms - should match CSS transition duration

    // Create overlay if it doesn't exist
    function createOverlay() {
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'mobile-menu-overlay';
            document.body.appendChild(overlay);
            
            // Add click handler to close menu when overlay is clicked
            overlay.addEventListener('click', function(e) {
                e.stopPropagation();
                if (sidebar.classList.contains('mobile-open')) {
                    toggleMobileMenu();
                }
            });
        }
        return overlay;
    }

    // Ensure overlay exists
    overlay = overlay || createOverlay();

    // Toggle mobile menu with animation
    function toggleMobileMenu() {
        if (isAnimating) return;
        
        isAnimating = true;
        const isOpening = !sidebar.classList.contains('mobile-open');
        
        if (isOpening) {
            // Show overlay first
            overlay.style.display = 'block';
            // Force reflow to ensure the element is rendered before adding active class
            void overlay.offsetWidth;
            
            // Then add active class to start the transition
            overlay.classList.add('active');
            
            // Then show the sidebar
            setTimeout(() => {
                sidebar.classList.add('mobile-open');
                html.classList.add('menu-open');
                isAnimating = false;
            }, 10);
        } else {
            // Start closing animation
            overlay.classList.remove('active');
            html.classList.remove('menu-open');
            
            // Wait for the overlay fade out before hiding the sidebar
            setTimeout(() => {
                sidebar.classList.remove('mobile-open');
                overlay.style.display = 'none';
                isAnimating = false;
            }, ANIMATION_DURATION);
        }
    }

    // Toggle menu when clicking the mobile menu button
    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleMobileMenu();
        });
    }

    // Close menu when clicking on overlay
    overlay.addEventListener('click', function(e) {
        e.stopPropagation();
        if (sidebar.classList.contains('mobile-open')) {
            toggleMobileMenu();
        }
    });

    // Close menu when clicking outside on mobile
    document.addEventListener('click', function(event) {
        if (window.innerWidth <= 992 && 
            !sidebar.contains(event.target) && 
            event.target !== mobileMenuBtn && 
            !mobileMenuBtn.contains(event.target)) {
            if (sidebar.classList.contains('mobile-open')) {
                toggleMobileMenu();
            }
        }
    });

    // Close menu when clicking a nav link on mobile
    document.querySelectorAll('.nav-link, .sidebar-nav a').forEach(link => {
        link.addEventListener('click', function() {
            if (window.innerWidth <= 992) {
                toggleMobileMenu();
            }
        });
    });

    // Handle window resize with debounce and RAF for performance
    let resizeTimeout;
    function handleResize() {
        if (window.innerWidth > 992) {
            // Reset mobile styles when resizing to desktop
            if (sidebar) {
                sidebar.classList.remove('mobile-open');
                sidebar.style.transform = '';
            }
            if (overlay) {
                overlay.classList.remove('active');
                overlay.style.display = 'none';
            }
            html.classList.remove('menu-open');
        }
    }

    // Use requestAnimationFrame for smoother resize handling
    function handleResizeWithRAF() {
        if (resizeTimeout) {
            cancelAnimationFrame(resizeTimeout);
        }
        resizeTimeout = requestAnimationFrame(() => {
            handleResize();
        });
    }

    // Add optimized resize event listener
    window.addEventListener('resize', handleResizeWithRAF);

    // Clean up event listeners when the page unloads
    window.addEventListener('beforeunload', function() {
        if (resizeTimeout) {
            cancelAnimationFrame(resizeTimeout);
        }
        window.removeEventListener('resize', handleResizeWithRAF);
    });

    // Initialize the sidebar state
    handleResize();
});