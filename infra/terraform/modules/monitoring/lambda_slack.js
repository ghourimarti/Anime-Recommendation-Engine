// Lambda: SNS → Slack webhook formatter.
//
// Receives a CloudWatch alarm SNS event,
// formats a colored Slack message (red=ALARM / green=OK / grey=INSUFFICIENT_DATA),
// posts to SLACK_WEBHOOK_URL.
//
// Runtime: nodejs20.x (built-in https module — zero deps).
//
// Trigger:    aws_sns_topic_subscription with protocol = "lambda"
// Env:        SLACK_WEBHOOK_URL (sensitive — set via TF var slack_webhook_url)

const https = require("https");
const { URL } = require("url");

const COLOR = {
  ALARM: "#d62728",                 // red
  OK: "#2ca02c",                    // green
  INSUFFICIENT_DATA: "#7f7f7f",     // grey
};

exports.handler = async (event) => {
  const webhookUrl = process.env.SLACK_WEBHOOK_URL;
  if (!webhookUrl) {
    console.error("SLACK_WEBHOOK_URL not set; refusing to silently drop message");
    throw new Error("SLACK_WEBHOOK_URL not configured");
  }

  // SNS wraps the CloudWatch alarm in event.Records[0].Sns.Message (JSON string).
  for (const record of event.Records || []) {
    const sns = record.Sns || {};
    let alarm;
    try {
      alarm = JSON.parse(sns.Message || "{}");
    } catch (e) {
      // Not a CloudWatch alarm payload — fall through and post the raw subject.
      alarm = { AlarmName: sns.Subject || "(unknown alarm)", NewStateValue: "ALARM", NewStateReason: sns.Message };
    }

    const state = alarm.NewStateValue || "ALARM";
    const color = COLOR[state] || "#1f77b4";
    const payload = {
      text: `*${alarm.AlarmName || "anime-recommender alert"}* — ${state}`,
      attachments: [
        {
          color,
          fields: [
            { title: "Region", value: alarm.Region || "us-east-1", short: true },
            { title: "Account", value: alarm.AWSAccountId || "?", short: true },
            { title: "Reason", value: truncate(alarm.NewStateReason || "(none)", 500), short: false },
            { title: "Description", value: truncate(alarm.AlarmDescription || "(none)", 300), short: false },
          ],
          footer: "anime-recommender · CloudWatch → Lambda → Slack",
          ts: Math.floor(Date.now() / 1000),
        },
      ],
    };

    await postJson(webhookUrl, payload);
  }
  return { statusCode: 200 };
};

function truncate(s, max) {
  if (typeof s !== "string") return String(s);
  return s.length <= max ? s : s.slice(0, max - 3) + "...";
}

function postJson(urlStr, body) {
  return new Promise((resolve, reject) => {
    const u = new URL(urlStr);
    const payload = JSON.stringify(body);
    const req = https.request(
      {
        hostname: u.hostname,
        port: u.port || 443,
        path: u.pathname + u.search,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload),
        },
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve({ statusCode: res.statusCode, body: data });
          } else {
            reject(new Error(`Slack webhook returned ${res.statusCode}: ${data}`));
          }
        });
      }
    );
    req.on("error", reject);
    req.write(payload);
    req.end();
  });
}
