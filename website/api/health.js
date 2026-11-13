// Health check for uptime monitors (UptimeRobot): GET /api/health -> 200 {"ok":true,...}
// If the domain ever points somewhere else (e.g. the old WordPress server), this path returns 404 and the monitor alerts.
module.exports = (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  res.status(200).json({ ok: true, site: 'twinroozi.com', time: new Date().toISOString() });
};
