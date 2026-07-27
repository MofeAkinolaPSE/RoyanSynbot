Morning CL, lets begin below are issues and modifications we need to make, post deployment. We are going to use this prompt information along with the images in the folder attached.

BUt ill specify best I can, so you understand the goal as always. Each point below, is as the clients described it. I took the images for pixel examination so you can see.There are also word documents we specify the Radiology template, (I don't fully understand how we intend to implement these templates, cause I scanned through and its all texts talking about the details of the scan, but I know they are meant to provide some sort of guidance into how the radiology department works, and we have to use the information, but more on that later, id need to talk to them to understand there workflows. Moving on.... Before we start taking on the problems, I think its best we understand what time of information is available to us, and classify those images/documents so we can apply them for pixel guidance, where needed. SO there are a lot of images, but I trust you can process them, understand what its contains and gather the valuable information and use it where its needed In respect to the prompt (clients requests). But im sure there is an image to go with each item on the prompt.  We got three images/doc folders, we start by processing all 3 or taking it one after the other/ But I think, like we said, just, process the information we gather first, so we know how to apply it.. Not the immunization images are important and each item should we sstored and be applied in the systems auto filling/drop down feature where needed(More details explained in the prompt)
15- Each department is there own business, ROyan LAb, RoyanPharma. ROyanRadiology(Scancare- this is the radiology department.) The MD whats to track the finances between all departments with the toggle of a button. ALso the Drugs/Services provided per which one went into HMO, or Staff or private Patient, we also want to track those financial information.

 15b-- look up how we can connect Mindray -(the is the Lab department tech, they rather just input the information from the Mindray test, manually into ROyanhealth Lab test template(with standards set by the attendant) , we'll get the exact template, for each test type, so the attendant can just put the test results into the Royanhealth result pop up cards, which would then update the patients information into the system and the Cprs reflects the update.

16 - Pharmacy need access to the Doctor prescribed notes, for all the historical context. ( so they have access to the cprs pages.) PAy attention to the Rbac, through this prompt, I'll keep dropping context, on who has access to what...
17. COnfirm patients allergy, reflects for all patients 
18 - The system should be able to register (patients can change HMO), Each Hmo comes with the Identify data,( we'll get the exact data later, unless its available to us in our hope exports.


19. Lab- each test in the lab is allowed to create the template (the required values), some of the lab images are attached in the folder, so the lab works like this, they use the Mindray equipment to run the tests and then manually get the values from the Mindray dashboard, and then input the data into our system( ROyanhealth), so we need to add the pop up box, per patient test, so after the test have been run the LAb attendant cant input the results into the result pages/pop up box, ( page could be more efficient). About the templates, we'll get them soon, lets just make sure we are ready for it.   

20- Build a claim process setup.- connect it to stripe.- similar to the billing setup. 

21. Segregation each HmO per month.
 Anchor(HMO) - patients using Anchor- in that month
- A pop up per Patient encounter showing the details of that encounter- for the HMO side for with the containing all the details down to the number of drugs. 

22 -Separate Pharmacy from Lab Billing based on HMO
- A centralized dashboarding showing who's in the hospital.-- we already have that- 
- The system should specify about the difference in Private and HMO services a create the report.
- Pharma 
- HMO billing different generate 
- Can the system calculate the BMI -- from the other information provided during the vitals I suppose, then we expose all that information in the vital pages in the cprs.

23 Pharmacy -
Adendum. - access to the patients past records
Needs access to all the Medical history 
-Inventory access/Inventory analysis, purchasing power, how revenue is relocated,
Expiry date alerts, low stock. 
- SOR- sales on return.
- Same stock for both HMO & Private. 
- A rule any stock showing expired from 2025, and stock showing Zero, better to add no stock, provide UI, to update stock, so they can manually input the stock.  

HMO approval
- Setup a signature, that's connects to a tab and when they sign it appears on the pharmacy patients history page. we then save the patients signature, its a means to confirm the patients actually collected the drugs prescribed, so lets design the backend logic to interact with the pad and pen and the application we need to download on the tab, that allows us handle that features. 
- A notification where a patients has been already prescribed a drug, so it down get prescribed again. 


Doctor. 
- Doctor needs access to Lab patient page/records. 


Nurse
- setup for baby delivery records , DOB, gender, time of delivery. A page for Babies, and then we tie the baby pages/data to the the Mother information., and then we tie the baby pages/data to the the Mother information., and then we tie the baby pages/data to the Mother information.
- Immunisation package/ records link to the Babies pages and details , check the DRM HOPE data 
- Can take multiple immunisation at once.

That's it for now CL, lets design a plan to implement this upgrades efficiently, BEgin your deep dive.