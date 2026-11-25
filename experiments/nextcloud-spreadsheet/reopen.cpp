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
  int opened=b.OpenFile(L"/private/tmp/spreadsheet-engines/nextcloud-edited.xlsx",L"");
  printf("open=%d\n",opened);fflush(stdout);
  if(!opened) {
   result=b.SaveFile(L"xlsx",L"/private/tmp/spreadsheet-engines/nextcloud-reopened.xlsx");printf("resave=%d\n",result);fflush(stdout);
   b.CloseFile();
  }
 }
 NSDoctRenderer::CDocBuilder::Dispose();
 return result;
}
