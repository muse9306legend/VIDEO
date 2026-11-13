// Click-to-load video players and footer year.
// Load each channel's latest-uploads playlist only when clicked (fast page, no YouTube cookies until then).
document.querySelectorAll('.ph[data-list]').forEach(function (box) {
  box.querySelector('button').addEventListener('click', function () {
    var f = document.createElement('iframe');
    f.src = 'https://www.youtube-nocookie.com/embed/videoseries?list=' + box.dataset.list + '&autoplay=1';
    f.title = 'YouTube 최신 영상';
    f.allow = 'autoplay; encrypted-media; picture-in-picture';
    f.allowFullscreen = true;
    box.replaceChildren(f);
  });
});
// A single YouTube video (data-video = video ID), also loaded only when clicked.
document.querySelectorAll('.ph[data-video]').forEach(function (box) {
  box.querySelector('button').addEventListener('click', function () {
    var f = document.createElement('iframe');
    f.src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(box.dataset.video) + '?autoplay=1&rel=0';
    f.title = box.dataset.title || 'YouTube 영상';
    f.allow = 'autoplay; encrypted-media; picture-in-picture';
    f.allowFullscreen = true;
    box.replaceChildren(f);
  });
});
// Vimeo: load the player only when clicked.
document.querySelectorAll('.vimeo[data-vimeo]').forEach(function (box) {
  box.querySelector('button').addEventListener('click', function () {
    var f = document.createElement('iframe');
    f.src = 'https://player.vimeo.com/video/' + box.dataset.vimeo + '?autoplay=1&dnt=1';
    f.title = box.dataset.title || 'Vimeo';
    f.allow = 'autoplay; fullscreen; picture-in-picture';
    f.allowFullscreen = true;
    box.replaceChildren(f);
  });
});
document.getElementById('y').textContent = new Date().getFullYear();
