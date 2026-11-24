/**
 * Bete Daniel Hotel - Lightweight Vanilla JavaScript
 * Handles responsive mobile navigation toggle and UI interactions.
 */

document.addEventListener('DOMContentLoaded', function () {
  const prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // 1. Mobile Navigation Toggle
  const navToggle = document.getElementById('navToggle');
  const navMenu = document.getElementById('navMenu');

  if (navToggle && navMenu) {
    navToggle.addEventListener('click', function () {
      const isExpanded = navToggle.getAttribute('aria-expanded') === 'true';
      navToggle.setAttribute('aria-expanded', !isExpanded);
      navMenu.classList.toggle('is-active');
    });

    // Close menu when clicking on a navigation link (for smooth anchor scrolling)
    const navLinks = navMenu.querySelectorAll('.nav-link');
    navLinks.forEach(function (link) {
      link.addEventListener('click', function () {
        navMenu.classList.remove('is-active');
        navToggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  // Keep the homepage navigation visible and frosted after the hero edge.
  const homeHeader = document.querySelector('.site-header-home');
  if (homeHeader) {
    const updateHeaderOnScroll = function () {
      homeHeader.classList.toggle('is-scrolled', window.scrollY > 40);
    };

    updateHeaderOnScroll();
    window.addEventListener('scroll', updateHeaderOnScroll, { passive: true });
  }

  // 2. Alert / Message Dismissal
  const dismissButtons = document.querySelectorAll('.message-dismiss');
  dismissButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      const messageItem = this.closest('.message-item');
      if (messageItem) {
        messageItem.style.opacity = '0';
        setTimeout(function () {
          messageItem.remove();
        }, 200);
      }
    });
  });

  // 3. Smooth scrolling for internal anchors with offset for sticky navbar
  document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
    anchor.addEventListener('click', function (e) {
      const targetId = this.getAttribute('href');
      if (targetId === '#') return;

      const targetEl = document.querySelector(targetId);
      if (targetEl) {
        e.preventDefault();
        const headerHeight = document.querySelector('.site-header')?.offsetHeight || 80;
        const targetPosition = targetEl.getBoundingClientRect().top + window.pageYOffset - headerHeight;

        window.scrollTo({
          top: targetPosition,
          behavior: prefersReducedMotion ? 'auto' : 'smooth'
        });
      }
    });
  });

  // 4. Subtle Viewport Scroll Reveal (IntersectionObserver)
  if ('IntersectionObserver' in window && !prefersReducedMotion) {
    const revealTargets = document.querySelectorAll(
      '.section-header, .about-card, .pillar-item, .room-card, .facility-card, .gallery-card, .contact-grid, .empty-state-card, .detail-layout'
    );

    if (revealTargets.length > 0) {
      document.documentElement.classList.add('js-reveal-enabled');
      const staggeredTargets = '.pillar-item, .room-card, .facility-card, .gallery-card';
      const staggerCounts = new Map();

      const revealObserver = new IntersectionObserver(function (entries, observer) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-revealed');

            if (entry.target.matches(staggeredTargets)) {
              const target = entry.target;
              const clearStaggerDelay = function (event) {
                if (event.target === target && event.propertyName === 'opacity') {
                  target.style.setProperty('--reveal-delay', '0ms');
                  target.removeEventListener('transitionend', clearStaggerDelay);
                }
              };

              target.addEventListener('transitionend', clearStaggerDelay);
            }

            observer.unobserve(entry.target);
          }
        });
      }, {
        root: null,
        threshold: 0.15
      });

      revealTargets.forEach(function (el) {
        el.classList.add('reveal-on-scroll');

        if (el.matches(staggeredTargets) && el.parentElement) {
          const index = staggerCounts.get(el.parentElement) || 0;
          el.style.setProperty('--reveal-delay', ((index + 1) * 100) + 'ms');
          staggerCounts.set(el.parentElement, index + 1);
        }

        revealObserver.observe(el);
      });
    }
  }
});
