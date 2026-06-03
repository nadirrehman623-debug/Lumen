// write a script to fetch chat data from the server and display it in the chat window
fetch('/chat/<session_id>', {
 method: "POST",
 headers: {
   "Content-Type": "application/json"
 },
 body: JSON.stringify({ 
}
