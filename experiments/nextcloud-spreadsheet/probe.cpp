#include "docbuilder.h"
#include <stdio.h>
int main() {
 const wchar_t* engine=L"/private/tmp/spreadsheet-engines/runtime";
 NSDoctRenderer::CDocBuilder::Initialize(engine);
 int result=1;
 {
  NSDoctRenderer::CDocBuilder b;
  b.SetProperty("--work-directory", engine);
  b.SetProperty("--check-fonts", L"false");
  
  b.SetTmpFolder(L"/private/tmp/spreadsheet-engines");
  int opened=b.OpenFile(L"/private/tmp/spreadsheet-engines/baseline.xlsx",L"");
  printf("open=%d\n",opened);fflush(stdout);
  if(!opened) {
   bool edited=b.ExecuteCommand(L"var s=Api.GetSheet('Review'); var r=s.GetRange('B2'); r.SetValue('Original wording | Proposed wording'); r.GetCharacters(1,16).GetFont().SetColor(Api.CreateColorFromRGB(192,0,0)); r.GetCharacters(20,16).GetFont().SetColor(Api.CreateColorFromRGB(0,128,0));");
   printf("edit=%d\n",edited);fflush(stdout);
   if(edited) {result=b.SaveFile(L"xlsx",L"/private/tmp/spreadsheet-engines/nextcloud-edited.xlsx");printf("save=%d\n",result);fflush(stdout);}
   b.CloseFile();
  }
 }
 NSDoctRenderer::CDocBuilder::Dispose();
 return result;
}
