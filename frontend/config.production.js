(function configureStretchCoach() {
  if (window.STRETCH_COACH_CONFIG) {
    return;
  }

  window.STRETCH_COACH_CONFIG = Object.freeze({
    appUrl: "https://sbuddy.leitnersoft.com",
    bucketName: "sbuddy.leitnersoft.com",
    cloudFrontDomain: "d1spztj11put9r.cloudfront.net",
    speechApiUrl: "https://hr9yi4qsmg.execute-api.us-east-1.amazonaws.com/api/speak",
    progressApiUrl: "https://hr9yi4qsmg.execute-api.us-east-1.amazonaws.com/api/exercise-completions",
    speechLambdaArn: "arn:aws:lambda:us-east-1:140023375269:function:stretch-coach-speech",
  });
})();
