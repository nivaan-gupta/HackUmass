/*
  

  Layout mapping (grid):
       1  2
       3  4
       5  6

  My wiring channels (0..5):
    ch0: EN=4,  IN1=16, IN2=17
    ch1: EN=19, IN1=5,  IN2=18
    ch2: EN=13, IN1=14, IN2=27
    ch3: EN=33, IN1=26, IN2=25
    ch4: EN=21, IN1=22, IN2=23
    ch5: EN=2*, IN1=15*, IN2=32  (*boot pins: if flaky, set EN=-1 and hard-tie HIGH)
*/

// ---------------- USER CONFIG ----------------
int IN1[6] = {16,  5, 14, 26, 22, 15};
int IN2[6] = {17, 18, 27, 25, 23, 32};
int EN [6] = { 4, 19, 13, 33, 21,  2};   

// Braille dot → channel mapping for grid 1 2 / 3 4 / 5 6
int DOT_MAP[6] = {0, 1, 2, 3, 4, 5};

// Timing & strength
const uint16_t DOT_ON_MS   = 180;
const uint16_t DOT_GAP_MS  = 60;
const uint16_t CHAR_GAP_MS = 220;
const uint16_t WORD_GAP_MS = 420;
int STRENGTH[6] = {200, 200, 200, 200, 200, 200};

// -------------- BRAILLE TABLES --------------
const uint8_t BRAILLE_CAPITAL = 0b100000;
const uint8_t BRAILLE_NUMBER  = 0b111100;

uint8_t letterMask(char c) {
  switch (c) {
    case 'a': return 0b000001; case 'b': return 0b000011; case 'c': return 0b000101;
    case 'd': return 0b001101; case 'e': return 0b001001; case 'f': return 0b000111;
    case 'g': return 0b001111; case 'h': return 0b001011; case 'i': return 0b000110;
    case 'j': return 0b001110; case 'k': return 0b010001; case 'l': return 0b010011;
    case 'm': return 0b010101; case 'n': return 0b011101; case 'o': return 0b011001;
    case 'p': return 0b010111; case 'q': return 0b011111; case 'r': return 0b011011;
    case 's': return 0b010110; case 't': return 0b011110; case 'u': return 0b110001;
    case 'v': return 0b110011; case 'w': return 0b101110; case 'x': return 0b110101;
    case 'y': return 0b111101; case 'z': return 0b111001; default: return 0;
  }
}
uint8_t punctMask(char c) {
  switch (c) {
    case ',': return 0b000010;
    case ';': return 0b000110;
    case ':': return 0b001010;
    case '.': return 0b011010;
    case '?': return 0b100010;
    case '!': return 0b010110;
    case '-': return 0b100100;
    case '\'': return 0b000100;
    case '"': return 0b100110;
    case '(': case ')': return 0b010110;
    default:  return 0;
  }
}
char digitAsLetter(char d) { if (d>='1'&&d<='9') return 'a'+(d-'1'); if (d=='0') return 'j'; return 0; }

// -------------- MOTOR HELPERS --------------
inline int chForDot(uint8_t dot){ return DOT_MAP[dot-1]; }

void chOn(int ch){
  digitalWrite(IN1[ch], LOW);
  digitalWrite(IN2[ch], HIGH);
  if (EN[ch] >= 0) analogWrite(EN[ch], STRENGTH[ch]); // 0..255
}
void chOff(int ch){
  if (EN[ch] >= 0) analogWrite(EN[ch], 0);
  digitalWrite(IN1[ch], LOW);
  digitalWrite(IN2[ch], LOW);
}
void allOff(){ for(int i=0;i<6;i++) chOff(i); }

void vibrateCell(uint8_t mask){
  for(int i=0;i<6;i++) if(mask & (1<<i)) chOn(chForDot(i+1));
  delay(DOT_ON_MS);
  allOff();
  delay(DOT_GAP_MS);
}

// -------------- EMIT LOGIC --------------
void emitChar(char c, bool &numbersMode){
  if (c==' ') { delay(WORD_GAP_MS); numbersMode=false; return; }
  uint8_t pm = punctMask(c);
  if (pm) { vibrateCell(pm); delay(CHAR_GAP_MS); numbersMode=false; return; }
  if (c>='0' && c<='9'){
    if (!numbersMode){ vibrateCell(BRAILLE_NUMBER); delay(CHAR_GAP_MS); numbersMode=true; }
    char base=digitAsLetter(c);
    vibrateCell(letterMask(base)); delay(CHAR_GAP_MS); return;
  }
  if ((c>='A'&&c<='Z')||(c>='a'&&c<='z')){
    bool up=(c>='A'&&c<='Z'); char lc=up?(c-'A'+'a'):c;
    if (up){ vibrateCell(BRAILLE_CAPITAL); delay(CHAR_GAP_MS); }
    uint8_t m=letterMask(lc); if (m){ vibrateCell(m); delay(CHAR_GAP_MS); }
    numbersMode=false; return;
  }
}
void emitString(const String &s){ bool n=false; for(size_t i=0;i<s.length(); ++i) emitChar(s[i], n); }

// -------------- SETUP --------------
void setup(){
  Serial.begin(115200);
  for(int i=0;i<6;i++){
    pinMode(IN1[i], OUTPUT);
    pinMode(IN2[i], OUTPUT);
    if (EN[i] >= 0) pinMode(EN[i], OUTPUT);
    chOff(i);
  }
  Serial.println("BrailleMotorDriver_AnalogWrite_Map ready. Type text or TESTMAP");
}

String line;
void loop(){
  while(Serial.available()){
    char c=Serial.read();
    if (c=='\r') continue;
    if (c=='\n'){
      if (line=="TESTMAP"){
        Serial.println("Buzzing dots 1..6 by mapping...");
        for(int d=1; d<=6; ++d){ Serial.print("Dot "); Serial.println(d); vibrateCell(1<<(d-1)); delay(200); }
      } else if (line.length()>0){
        Serial.print("Emit: "); Serial.println(line);
        emitString(line);
      }
      line="";
    } else {
      line += c;
    }
  }
}
